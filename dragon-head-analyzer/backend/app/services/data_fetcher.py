"""
数据获取服务 - AKShare + 多源回退 + 本地磁盘缓存

策略：
1. 优先使用 akshare/efinance（走 eastmoney 等数据源）
2. eastmoney 接口失败时自动回退到备用数据源（新浪/腾讯）
3. 所有数据自动缓存到本地磁盘（JSON），避免重复请求
4. 请求间随机延迟，模拟人类行为，避免触发反爬
5. 30天自动清理过期缓存
"""
import akshare as ak
import efinance as ef
import pandas as pd
import numpy as np
import json
import os
import time
import random
import hashlib
import traceback
import requests
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path


# =============================================================================
# 磁盘缓存管理
# =============================================================================
class DiskCache:
    """
    基于 JSON 文件的磁盘缓存
    缓存目录: backend/data_cache/
    每个 key 对应一个 JSON 文件，文件名是 key 的 MD5
    文件内包含 { "data": ..., "timestamp": ..., "key": ... }
    """

    def __init__(self, cache_dir: str = None, default_ttl: int = 3600, max_age_days: int = 30):
        if cache_dir is None:
            base = Path(__file__).resolve().parent.parent.parent
            cache_dir = str(base / "data_cache")
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl  # 秒
        self.max_age_days = max_age_days

    def _key_to_path(self, key: str) -> Path:
        safe = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{safe}.json"

    def get(self, key: str, ttl: int = None) -> Optional[dict]:
        """获取缓存数据，过期返回 None"""
        if ttl is None:
            ttl = self.default_ttl
        path = self._key_to_path(key)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                record = json.load(f)
            age = time.time() - record.get("timestamp", 0)
            if age > ttl:
                return None  # 过期
            return record.get("data")
        except (json.JSONDecodeError, IOError):
            return None

    def set(self, key: str, data):
        """写入缓存"""
        path = self._key_to_path(key)
        record = {
            "key": key,
            "timestamp": time.time(),
            "data": data,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, default=str)
        except IOError as e:
            print(f"[DiskCache] 写入缓存失败: {e}")

    def get_or_set(self, key: str, fetch_fn, ttl: int = None):
        """缓存命中则返回，否则调用 fetch_fn 获取并缓存"""
        cached = self.get(key, ttl)
        if cached is not None:
            return cached
        data = fetch_fn()
        if data is not None:
            self.set(key, data)
        return data

    def cleanup(self):
        """清理超过 max_age_days 的缓存文件"""
        cutoff = time.time() - self.max_age_days * 86400
        count = 0
        for f in self.cache_dir.glob("*.json"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                count += 1
        if count:
            print(f"[DiskCache] 清理了 {count} 个过期缓存文件")


# =============================================================================
# 请求工具（随机延迟 + UA 伪装）
# =============================================================================
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

# 请求间最小/最大延迟（秒）
DELAY_MIN = 0.5
DELAY_MAX = 2.0


def polite_delay():
    """请求间随机延迟，避免高频触发反爬"""
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get_random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": "https://quote.eastmoney.com/",
    }


# =============================================================================
# 备用数据源：新浪/腾讯 HTTP 接口
# =============================================================================
class SinaStockAPI:
    """新浪财经 API（备用数据源）"""

    BASE = "https://hq.sinajs.cn/list="
    REALTIME = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    @staticmethod
    def get_realtime_quotes(codes: list = None) -> list:
        """
        获取实时行情（新浪）
        如果 codes 为空则返回空
        """
        if not codes:
            return []
        try:
            # 新浪代码格式：sh600000 / sz000001
            sina_codes = []
            for c in codes[:80]:  # 限制批量
                c = str(c).strip()
                if c.startswith("6"):
                    sina_codes.append(f"sh{c}")
                else:
                    sina_codes.append(f"sz{c}")

            url = SinaStockAPI.BASE + ",".join(sina_codes)
            resp = requests.get(url, headers=get_random_headers(), timeout=10)
            resp.encoding = "gbk"
            results = []
            for line in resp.text.strip().split("\n"):
                if "=" not in line:
                    continue
                parts = line.split("=")[1].strip('";').split(",")
                if len(parts) >= 32:
                    code_raw = line.split("_")[2][:6]
                    results.append({
                        "代码": code_raw,
                        "名称": parts[0],
                        "开盘": float(parts[1]) if parts[1] else 0,
                        "昨收": float(parts[2]) if parts[2] else 0,
                        "最新价": float(parts[3]) if parts[3] else 0,
                        "最高": float(parts[4]) if parts[4] else 0,
                        "最低": float(parts[5]) if parts[5] else 0,
                        "成交量": int(parts[8]) if parts[8] else 0,
                        "成交额": float(parts[9]) if parts[9] else 0,
                        "日期": parts[30],
                        "时间": parts[31],
                    })
            return results
        except Exception as e:
            print(f"[SinaAPI] 获取实时行情失败: {e}")
            return []

    @staticmethod
    def get_kline(code: str, scale: str = "240", datalen: int = 60) -> list:
        """
        获取K线数据（新浪）
        scale: 5/15/30/60/240（分钟），240=日线
        """
        try:
            market = "sh" if code.startswith("6") else "sz"
            params = {
                "symbol": f"{market}{code}",
                "scale": scale,
                "ma": "no",
                "datalen": datalen,
            }
            resp = requests.get(
                SinaStockAPI.REALTIME,
                params=params,
                headers=get_random_headers(),
                timeout=10,
            )
            data = resp.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[SinaAPI] 获取K线失败({code}): {e}")
            return []


# =============================================================================
# 主数据获取器
# =============================================================================
class DataFetcher:
    """
    A股数据获取器（多源回退 + 磁盘缓存）

    缓存策略：
    - 涨停池/炸板池：交易时间缓存 60s，盘后缓存 24h
    - 实时行情：缓存 10s
    - 历史K线：缓存 24h（日线数据不变）
    - 板块数据：缓存 120s
    """

    def __init__(self):
        self.cache = DiskCache(default_ttl=60, max_age_days=30)
        # 启动时清理过期缓存
        self.cache.cleanup()

    # =========================================================================
    # 涨停池
    # =========================================================================
    def get_zt_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """获取涨停股池（东财 → 缓存 → 备用）"""
        date_str = trade_date or datetime.now().strftime("%Y%m%d")
        cache_key = f"zt_pool_{date_str}"
        ttl = self._market_ttl()

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        df = self._fetch_zt_pool_akshare(date_str)
        if df.empty:
            df = self._fetch_zt_pool_fallback(date_str)

        if not df.empty:
            self.cache.set(cache_key, self._df_to_records(df))
        return df

    def _fetch_zt_pool_akshare(self, date_str: str) -> pd.DataFrame:
        """AKShare 涨停池"""
        polite_delay()
        try:
            df = ak.stock_zt_pool_em(date=date_str)
            print(f"[DataFetcher] AKShare 涨停池获取成功: {len(df)} 条")
            return df
        except Exception as e:
            print(f"[DataFetcher] AKShare 涨停池失败: {e}")
            return pd.DataFrame()

    def _fetch_zt_pool_fallback(self, date_str: str) -> pd.DataFrame:
        """
        涨停池备用方案
        通过实时行情筛选涨幅>=9.9%的股票（近似）
        """
        print(f"[DataFetcher] 尝试涨停池备用方案...")
        polite_delay()
        try:
            df = ef.stock.get_realtime_quotes()
            if df.empty:
                return pd.DataFrame()
            # 筛选涨幅接近涨停的
            if "涨跌幅" in df.columns:
                zt = df[df["涨跌幅"] >= 9.8].copy()
                zt["连板数"] = 0  # 备用方案无法获取连板数
                zt["封单额"] = 0
                return zt
            return pd.DataFrame()
        except Exception as e:
            print(f"[DataFetcher] 涨停池备用方案也失败: {e}")
            return pd.DataFrame()

    # =========================================================================
    # 连板池
    # =========================================================================
    def get_lb_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """连板池（从涨停池筛选连板数>1）"""
        try:
            zt = self.get_zt_pool(trade_date)
            if zt.empty:
                return pd.DataFrame()
            if "连板数" in zt.columns:
                return zt[zt["连板数"] > 1].copy()
            return pd.DataFrame()
        except Exception as e:
            print(f"[DataFetcher] 获取连板池失败: {e}")
            return pd.DataFrame()

    # =========================================================================
    # 炸板池
    # =========================================================================
    def get_zr_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """获取炸板股池"""
        date_str = trade_date or datetime.now().strftime("%Y%m%d")
        cache_key = f"zr_pool_{date_str}"
        ttl = self._market_ttl()

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ak.stock_zt_pool_zbgc_em(date=date_str)
            print(f"[DataFetcher] 炸板池获取成功: {len(df)} 条")
            if not df.empty:
                self.cache.set(cache_key, self._df_to_records(df))
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取炸板池失败: {e}")
            return pd.DataFrame()

    # =========================================================================
    # 实时行情
    # =========================================================================
    def get_realtime_quotes(self) -> pd.DataFrame:
        """全市场实时行情快照（efinance → 缓存）"""
        cache_key = "realtime_quotes"
        ttl = 10  # 实时数据 10 秒缓存

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ef.stock.get_realtime_quotes()
            if not df.empty:
                self.cache.set(cache_key, self._df_to_records(df))
            return df
        except Exception as e:
            print(f"[DataFetcher] efinance 实时行情失败: {e}")
            # 备用：新浪行情（需要代码列表，此处仅作为 fallback 提示）
            return pd.DataFrame()

    # =========================================================================
    # 分时K线
    # =========================================================================
    def get_minute_kline(self, code: str, period: str = "1") -> pd.DataFrame:
        """
        获取分时K线（akshare → 新浪备用 → 缓存 24h）
        period: 1/5/15/30/60 分钟
        """
        cache_key = f"minute_kline_{code}_{period}"
        ttl = 3600  # 分钟线缓存 1 小时

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        # 方案1: akshare
        polite_delay()
        df = self._fetch_minute_kline_akshare(code, period)

        # 方案2: 新浪备用
        if df.empty:
            df = self._fetch_minute_kline_sina(code, period)

        if not df.empty:
            self.cache.set(cache_key, self._df_to_records(df))
        return df

    def _fetch_minute_kline_akshare(self, code: str, period: str) -> pd.DataFrame:
        try:
            df = ak.stock_zh_a_hist_min_em(
                symbol=code, period=period, adjust="qfq"
            )
            return df
        except Exception as e:
            print(f"[DataFetcher] akshare 分时K线失败({code}): {e}")
            return pd.DataFrame()

    def _fetch_minute_kline_sina(self, code: str, period: str) -> pd.DataFrame:
        """新浪备用分时K线"""
        polite_delay()
        try:
            scale_map = {"1": "1", "5": "5", "15": "15", "30": "30", "60": "60"}
            scale = scale_map.get(period, "5")
            data = SinaStockAPI.get_kline(code, scale=scale, datalen=240)
            if not data:
                return pd.DataFrame()

            records = []
            for d in data:
                records.append({
                    "时间": d.get("day", ""),
                    "开盘": float(d.get("open", 0)),
                    "收盘": float(d.get("close", 0)),
                    "最高": float(d.get("high", 0)),
                    "最低": float(d.get("low", 0)),
                    "成交量": int(d.get("volume", 0)),
                    "成交额": 0,
                })
            df = pd.DataFrame(records)
            print(f"[DataFetcher] 新浪分时K线成功({code}): {len(df)} 条")
            return df
        except Exception as e:
            print(f"[DataFetcher] 新浪分时K线失败({code}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 日线历史数据（30天）
    # =========================================================================
    def get_stock_history(self, code: str, period: str = "daily",
                          start_date: str = None, end_date: str = None,
                          days: int = 30) -> pd.DataFrame:
        """
        获取日线历史数据
        默认只取最近 30 天，减少请求量
        缓存 24h（日线数据不会变）
        """
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

        cache_key = f"history_{code}_{period}_{start_date}_{end_date}"
        ttl = 86400  # 日线缓存 24 小时

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        # 方案1: akshare
        polite_delay()
        df = self._fetch_history_akshare(code, period, start_date, end_date)

        # 方案2: 新浪备用
        if df.empty:
            df = self._fetch_history_sina(code, days)

        if not df.empty:
            self.cache.set(cache_key, self._df_to_records(df))
        return df

    def _fetch_history_akshare(self, code: str, period: str,
                                start_date: str, end_date: str) -> pd.DataFrame:
        try:
            df = ak.stock_zh_a_hist(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date, adjust="qfq"
            )
            return df
        except Exception as e:
            print(f"[DataFetcher] akshare 日线失败({code}): {e}")
            return pd.DataFrame()

    def _fetch_history_sina(self, code: str, days: int = 30) -> pd.DataFrame:
        """新浪备用日线"""
        polite_delay()
        try:
            data = SinaStockAPI.get_kline(code, scale="240", datalen=days)
            if not data:
                return pd.DataFrame()

            records = []
            for d in data:
                open_p = float(d.get("open", 0))
                close_p = float(d.get("close", 0))
                records.append({
                    "日期": d.get("day", ""),
                    "开盘": open_p,
                    "收盘": close_p,
                    "最高": float(d.get("high", 0)),
                    "最低": float(d.get("low", 0)),
                    "成交量": int(d.get("volume", 0)),
                    "成交额": 0,
                    "振幅": 0,
                    "涨跌幅": round((close_p - open_p) / open_p * 100, 2) if open_p > 0 else 0,
                    "涨跌额": round(close_p - open_p, 2),
                    "换手率": 0,
                })
            df = pd.DataFrame(records)
            print(f"[DataFetcher] 新浪日线成功({code}): {len(df)} 条")
            return df
        except Exception as e:
            print(f"[DataFetcher] 新浪日线失败({code}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 板块数据
    # =========================================================================
    def get_board_list(self, board_type: str = "概念板块") -> pd.DataFrame:
        """获取板块列表及涨幅排名"""
        cache_key = f"board_{board_type}"
        ttl = 120  # 板块数据缓存 2 分钟

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            if board_type == "概念板块":
                df = ak.stock_board_concept_name_em()
            else:
                df = ak.stock_board_industry_name_em()
            if not df.empty:
                self.cache.set(cache_key, self._df_to_records(df))
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取板块列表失败: {e}")
            return pd.DataFrame()

    def get_board_stocks(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股"""
        cache_key = f"board_stocks_{board_name}"
        ttl = 300

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ak.stock_board_concept_cons_em(symbol=board_name)
            if not df.empty:
                self.cache.set(cache_key, self._df_to_records(df))
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取板块成分股失败({board_name}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 资金流向
    # =========================================================================
    def get_fund_flow_individual(self, code: str) -> pd.DataFrame:
        """获取个股资金流向"""
        cache_key = f"fund_flow_{code}"
        ttl = 300

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            market = "sh" if code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=code, market=market)
            if not df.empty:
                self.cache.set(cache_key, self._df_to_records(df))
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取资金流向失败({code}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 龙虎榜
    # =========================================================================
    def get_lhb_data(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """获取龙虎榜数据"""
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")

        cache_key = f"lhb_{trade_date}"
        ttl = 86400

        cached = self.cache.get(cache_key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ak.stock_lhb_detail_em(start_date=trade_date, end_date=trade_date)
            if not df.empty:
                self.cache.set(cache_key, self._df_to_records(df))
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取龙虎榜失败: {e}")
            return pd.DataFrame()

    # =========================================================================
    # 工具方法
    # =========================================================================
    def _market_ttl(self) -> int:
        """
        根据当前时间返回合适的缓存 TTL
        交易时间（9:15-15:00）：短 TTL
        盘后/周末：长 TTL
        """
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()

        # 周末直接用 24h 缓存
        if weekday >= 5:
            return 86400

        # 交易时间：60s
        if 9 <= hour < 16:
            return 60

        # 盘前盘后：300s
        return 300

    def _df_to_records(self, df: pd.DataFrame) -> list:
        """DataFrame 转 JSON 可序列化的 list[dict]"""
        records = df.replace({np.nan: None}).to_dict(orient="records")
        return records

    def clear_cache(self, prefix: str = None):
        """手动清理缓存"""
        count = 0
        for f in self.cache.cache_dir.glob("*.json"):
            if prefix:
                try:
                    with open(f, "r") as fh:
                        record = json.load(fh)
                    if record.get("key", "").startswith(prefix):
                        f.unlink()
                        count += 1
                except Exception:
                    pass
            else:
                f.unlink()
                count += 1
        print(f"[DataFetcher] 清理了 {count} 个缓存文件")
