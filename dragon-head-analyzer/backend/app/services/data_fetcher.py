"""
数据获取服务

架构：
  数据分为两类，策略不同：

  A. 核心数据（仅东方财富提供）
     涨停池、炸板池、连板数、封单额、龙虎榜、板块排名、资金流向
     → 只能走 akshare（底层是东方财富网页/接口）
     → 无真正替代源，失败即失败，靠缓存兜底

  B. 通用数据（多源可替代）
     实时行情、日线K线、分钟K线
     → akshare/efinance → 新浪 → 腾讯，真正的多源回退

  缓存策略：
     - 所有数据写本地 JSON 缓存（30天自动清理）
     - 交易时段短 TTL，盘后/周末长 TTL
     - 核心数据失败时返回过期缓存（stale-while-revalidate）

  反反爬：
     - 请求间随机延迟 0.5~2s
     - UA 轮换
     - Referer 伪装
"""
import akshare as ak
import efinance as ef
import pandas as pd
import numpy as np
import json
import time
import random
import hashlib
import logging
import requests
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from functools import wraps

logger = logging.getLogger(__name__)


def retry(max_attempts=3, delay=1.0, backoff=2.0, exceptions=(Exception,)):
    """指数退避重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exc = None
            wait = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        logger.warning(f"[Retry] {func.__name__} 第{attempt}次失败: {e}, {wait:.1f}s后重试")
                        time.sleep(wait)
                        wait *= backoff
            raise last_exc
        return wrapper
    return decorator


# =============================================================================
# 磁盘缓存
# =============================================================================
class DiskCache:
    """
    基于 JSON 文件的磁盘缓存
    缓存目录: backend/data_cache/
    每个 key → 一个 JSON 文件（MD5 命名）
    内容: { "data": ..., "timestamp": ..., "key": ... }
    """

    def __init__(self, cache_dir: str = None, max_age_days: int = 30):
        if cache_dir is None:
            base = Path(__file__).resolve().parent.parent.parent
            cache_dir = str(base / "data_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_age_days = max_age_days

    def _key_to_path(self, key: str) -> Path:
        safe = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{safe}.json"

    def get(self, key: str, ttl: int) -> Optional[dict]:
        """获取缓存，未过期返回 data，过期返回 None"""
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            if time.time() - record.get("timestamp", 0) > ttl:
                return None
            return record.get("data")
        except (json.JSONDecodeError, IOError):
            return None

    def get_stale(self, key: str) -> Optional[dict]:
        """获取缓存（忽略过期），用于核心数据降级"""
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            return record.get("data")
        except (json.JSONDecodeError, IOError):
            return None

    def set(self, key: str, data):
        """写入缓存"""
        path = self._key_to_path(key)
        record = {"key": key, "timestamp": time.time(), "data": data}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, default=str)
        except IOError as e:
            logger.info(f"[Cache] 写入失败: {e}")

    def cleanup(self):
        """清理超过 max_age_days 的缓存"""
        cutoff = time.time() - self.max_age_days * 86400
        count = 0
        for f in self.cache_dir.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                count += 1
        if count:
            logger.info(f"[Cache] 清理 {count} 个过期文件")


# =============================================================================
# 请求工具
# =============================================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36",
]


def polite_delay():
    """随机延迟 0.5~2s"""
    time.sleep(random.uniform(0.5, 2.0))


def random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


# =============================================================================
# 新浪 API（真正的备用数据源，仅覆盖通用数据）
# =============================================================================
class SinaAPI:
    """新浪财经 HTTP 接口——仅覆盖行情/K线，不覆盖涨停池等核心数据"""

    HQ_URL = "https://hq.sinajs.cn/list="
    KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    @staticmethod
    def get_realtime(codes: list) -> list:
        """实时行情（需传入代码列表）"""
        if not codes:
            return []
        sina_codes = []
        for c in codes[:80]:
            c = str(c).strip()
            prefix = "sh" if c.startswith("6") else "sz"
            sina_codes.append(f"{prefix}{c}")
        try:
            url = SinaAPI.HQ_URL + ",".join(sina_codes)
            resp = requests.get(url, headers=random_headers(), timeout=10)
            resp.encoding = "gbk"
            results = []
            for line in resp.text.strip().split("\n"):
                if "=" not in line:
                    continue
                parts = line.split("=")[1].strip('";').split(",")
                if len(parts) >= 32:
                    code_raw = line.split("_")[2][:6]
                    results.append({
                        "代码": code_raw, "名称": parts[0],
                        "开盘": float(parts[1] or 0), "昨收": float(parts[2] or 0),
                        "最新价": float(parts[3] or 0), "最高": float(parts[4] or 0),
                        "最低": float(parts[5] or 0),
                        "成交量": int(parts[8] or 0), "成交额": float(parts[9] or 0),
                        "日期": parts[30], "时间": parts[31],
                    })
            return results
        except Exception as e:
            logger.info(f"[Sina] 实时行情失败: {e}")
            return []

    @staticmethod
    def get_kline(code: str, scale: str = "240", datalen: int = 60) -> list:
        """
        K线数据
        scale: 5/15/30/60/240（分钟），240=日线
        """
        market = "sh" if code.startswith("6") else "sz"
        try:
            resp = requests.get(
                SinaAPI.KLINE_URL,
                params={"symbol": f"{market}{code}", "scale": scale, "ma": "no", "datalen": datalen},
                headers=random_headers(), timeout=10,
            )
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.info(f"[Sina] K线失败({code}): {e}")
            return []


# =============================================================================
# TTL 策略
# =============================================================================
def _market_ttl() -> int:
    """根据当前时间返回缓存 TTL"""
    now = datetime.now()
    if now.weekday() >= 5:
        return 86400  # 周末
    if 9 <= now.hour < 16:
        return 60      # 交易时间
    return 300         # 盘前/盘后


# =============================================================================
# 主数据获取器
# =============================================================================
class DataFetcher:
    """
    A股数据获取器

    核心数据（仅东方财富）：涨停池、炸板池、板块、资金流、龙虎榜
      → 失败时返回过期缓存（stale），不假装有备用

    通用数据（多源）：实时行情、日线K线、分钟K线
      → akshare/efinance → 新浪 真回退
    """

    def __init__(self):
        self.cache = DiskCache(max_age_days=30)
        self.cache.cleanup()

    # =========================================================================
    # 涨停池（核心数据，仅东方财富）
    # =========================================================================
    def get_zt_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        涨停股池——数据源: akstock_zt_pool_em (东方财富)
        无替代数据源，失败返回过期缓存
        """
        date_str = trade_date or datetime.now().strftime("%Y%m%d")
        key = f"zt_pool_{date_str}"
        ttl = _market_ttl()

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = self._fetch_zt_pool_with_retry(date_str)
            logger.info(f"[EM] 涨停池 {date_str}: {len(df)} 条")
            if not df.empty:
                self.cache.set(key, self._to_records(df))
            return df
        except Exception as e:
            logger.error(f"[EM] 涨停池失败(重试耗尽): {e}")
            stale = self.cache.get_stale(key)
            if stale is not None:
                logger.info(f"[EM] 涨停池使用过期缓存")
                return pd.DataFrame(stale)
            return pd.DataFrame()

    @retry(max_attempts=3, delay=2.0)
    def _fetch_zt_pool_with_retry(self, date_str: str) -> pd.DataFrame:
        df = ak.stock_zt_pool_em(date=date_str)
        if df is None:
            raise ValueError("涨停池返回None")
        return df

    def get_lb_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """连板池（从涨停池筛选连板数>1）"""
        zt = self.get_zt_pool(trade_date)
        if zt.empty or "连板数" not in zt.columns:
            return pd.DataFrame()
        return zt[zt["连板数"] > 1].copy()

    def get_zr_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        炸板股池——数据源: akstock_zt_pool_zbgc_em (东方财富)
        无替代数据源
        """
        date_str = trade_date or datetime.now().strftime("%Y%m%d")
        key = f"zr_pool_{date_str}"
        ttl = _market_ttl()

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = self._fetch_zr_pool_with_retry(date_str)
            logger.info(f"[EM] 炸板池 {date_str}: {len(df)} 条")
            if not df.empty:
                self.cache.set(key, self._to_records(df))
            return df
        except Exception as e:
            logger.error(f"[EM] 炸板池失败(重试耗尽): {e}")
            stale = self.cache.get_stale(key)
            if stale is not None:
                return pd.DataFrame(stale)
            return pd.DataFrame()

    @retry(max_attempts=3, delay=2.0)
    def _fetch_zr_pool_with_retry(self, date_str: str) -> pd.DataFrame:
        df = ak.stock_zt_pool_zbgc_em(date=date_str)
        if df is None:
            raise ValueError("炸板池返回None")
        return df

    # =========================================================================
    # 实时行情（通用数据，多源回退）
    # =========================================================================
    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        全市场实时行情
        源1: efinance（东方财富）→ 源2: 新浪
        """
        key = "realtime_quotes"
        ttl = 10

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        # 源1: efinance
        polite_delay()
        try:
            df = ef.stock.get_realtime_quotes()
            if not df.empty:
                self.cache.set(key, self._to_records(df))
                return df
        except Exception as e:
            logger.info(f"[EF] 实时行情失败: {e}")

        # 源2: 新浪（需要代码列表，这里无法全量获取，返回空）
        logger.info("[Sina] 实时行情备用源不支持全量获取，跳过")
        return pd.DataFrame()

    # =========================================================================
    # 分钟K线（通用数据，多源回退）
    # =========================================================================
    def get_minute_kline(self, code: str, period: str = "5") -> pd.DataFrame:
        """
        分钟K线
        源1: akshare（东方财富）→ 源2: 新浪
        """
        key = f"min_kline_{code}_{period}"
        ttl = 3600

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        # 源1: akshare
        polite_delay()
        try:
            df = ak.stock_zh_a_hist_min_em(symbol=code, period=period, adjust="qfq")
            if not df.empty:
                self.cache.set(key, self._to_records(df))
                return df
        except Exception as e:
            logger.info(f"[EM] 分钟K线失败({code}): {e}")

        # 源2: 新浪
        polite_delay()
        try:
            data = SinaAPI.get_kline(code, scale=period, datalen=240)
            if data:
                records = [{
                    "时间": d.get("day", ""), "开盘": float(d.get("open", 0)),
                    "收盘": float(d.get("close", 0)), "最高": float(d.get("high", 0)),
                    "最低": float(d.get("low", 0)), "成交量": int(d.get("volume", 0)),
                    "成交额": 0,
                } for d in data]
                df = pd.DataFrame(records)
                logger.info(f"[Sina] 分钟K线成功({code}): {len(df)} 条")
                self.cache.set(key, self._to_records(df))
                return df
        except Exception as e:
            logger.info(f"[Sina] 分钟K线失败({code}): {e}")

        return pd.DataFrame()

    # =========================================================================
    # 日线K线（通用数据，多源回退，30天）
    # =========================================================================
    def get_stock_history(self, code: str, period: str = "daily",
                          start_date: str = None, end_date: str = None,
                          days: int = 30) -> pd.DataFrame:
        """
        日线历史数据（默认30天）
        源1: akshare（东方财富）→ 源2: 新浪
        缓存 24h（日线数据不变）
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

        key = f"hist_{code}_{period}_{start_date}_{end_date}"
        ttl = 86400

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        # 源1: akshare
        polite_delay()
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date, adjust="qfq"
            )
            if not df.empty:
                self.cache.set(key, self._to_records(df))
                return df
        except Exception as e:
            logger.info(f"[EM] 日线失败({code}): {e}")

        # 源2: 新浪
        polite_delay()
        try:
            data = SinaAPI.get_kline(code, scale="240", datalen=days)
            if data:
                records = []
                for d in data:
                    o, c = float(d.get("open", 0)), float(d.get("close", 0))
                    records.append({
                        "日期": d.get("day", ""), "开盘": o, "收盘": c,
                        "最高": float(d.get("high", 0)),
                        "最低": float(d.get("low", 0)),
                        "成交量": int(d.get("volume", 0)),
                        "成交额": 0, "振幅": 0,
                        "涨跌幅": round((c - o) / o * 100, 2) if o > 0 else 0,
                        "涨跌额": round(c - o, 2), "换手率": 0,
                    })
                df = pd.DataFrame(records)
                logger.info(f"[Sina] 日线成功({code}): {len(df)} 条")
                self.cache.set(key, self._to_records(df))
                return df
        except Exception as e:
            logger.info(f"[Sina] 日线失败({code}): {e}")

        return pd.DataFrame()

    # =========================================================================
    # 板块数据（核心数据，仅东方财富）
    # =========================================================================
    def get_board_list(self, board_type: str = "概念板块") -> pd.DataFrame:
        """
        板块排名——数据源: akstock_board_concept/industry_name_em (东方财富)
        """
        key = f"board_{board_type}"
        ttl = 120

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            if board_type == "概念板块":
                df = ak.stock_board_concept_name_em()
            else:
                df = ak.stock_board_industry_name_em()
            if not df.empty:
                self.cache.set(key, self._to_records(df))
            return df
        except Exception as e:
            logger.info(f"[EM] 板块数据失败: {e}")
            stale = self.cache.get_stale(key)
            if stale is not None:
                return pd.DataFrame(stale)
            return pd.DataFrame()

    def get_board_stocks(self, board_name: str) -> pd.DataFrame:
        """板块成分股（东方财富）"""
        key = f"board_cons_{board_name}"
        ttl = 300

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ak.stock_board_concept_cons_em(symbol=board_name)
            if not df.empty:
                self.cache.set(key, self._to_records(df))
            return df
        except Exception as e:
            logger.info(f"[EM] 板块成分股失败({board_name}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 资金流向（核心数据，仅东方财富）
    # =========================================================================
    def get_fund_flow_individual(self, code: str) -> pd.DataFrame:
        """
        个股资金流向——数据源: akstock_individual_fund_flow (东方财富)
        """
        key = f"fund_flow_{code}"
        ttl = 300

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            market = "sh" if code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=code, market=market)
            if not df.empty:
                self.cache.set(key, self._to_records(df))
            return df
        except Exception as e:
            logger.info(f"[EM] 资金流向失败({code}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 龙虎榜（核心数据，仅东方财富）
    # =========================================================================
    def get_lhb_data(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        龙虎榜——数据源: akstock_lhb_detail_em (东方财富)
        """
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        key = f"lhb_{trade_date}"
        ttl = 86400

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ak.stock_lhb_detail_em(start_date=trade_date, end_date=trade_date)
            if not df.empty:
                self.cache.set(key, self._to_records(df))
            return df
        except Exception as e:
            logger.info(f"[EM] 龙虎榜失败: {e}")
            return pd.DataFrame()

    # =========================================================================
    # 工具
    # =========================================================================
    def _to_records(self, df: pd.DataFrame) -> list:
        return df.replace({np.nan: None}).to_dict(orient="records")

    def clear_cache(self, prefix: str = None):
        """清理缓存"""
        count = 0
        for f in self.cache.cache_dir.glob("*.json"):
            if prefix:
                try:
                    with open(f, "r") as fh:
                        if json.load(fh).get("key", "").startswith(prefix):
                            f.unlink()
                            count += 1
                except Exception:
                    pass
            else:
                f.unlink()
                count += 1
        logger.info(f"[Cache] 清理 {count} 个文件")
