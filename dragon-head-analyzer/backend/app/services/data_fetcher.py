"""
数据获取服务 v3 — 自适应多源故障转移架构

核心机制：
  SourceRegistry 管理每类数据的多个实现源
  每个源有动态健康分（0-100），连续失败扣分，成功恢复
  失败≥3次 → 降级（优先级降低），其他源自动提升
  成功 → 逐步恢复健康分

数据源分类：
  A. 核心数据（仅东方财富，无替代源）→ 降级策略：过期缓存
  B. 通用数据（多源可替代）→ 降级策略：切换下一个源

架构：
  ┌─────────────────────────────────────────────────┐
  │                 SourceRegistry                   │
  │  每类数据 → [Source₁(健康分), Source₂, ...]     │
  │  按优先级排序，失败降级，成功恢复                 │
  ├─────────────────────────────────────────────────┤
  │                 DiskCache                        │
  │  JSON 文件缓存，核心数据 stale-while-revalidate  │
  └─────────────────────────────────────────────────┘
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
import threading
import requests
from datetime import datetime, timedelta
from typing import Optional, Callable
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# =============================================================================
# 自适应数据源注册表
# =============================================================================
@dataclass
class SourceEntry:
    """单个数据源条目"""
    name: str                       # 源名称，如 "akshare_EM", "sina"
    fetch_fn: Callable              # 获取函数
    priority: int = 100             # 优先级（越高越先尝试）
    health: int = 100               # 健康分 0-100
    consecutive_failures: int = 0   # 连续失败次数
    total_calls: int = 0            # 总调用次数
    total_failures: int = 0         # 总失败次数
    last_failure_time: float = 0    # 上次失败时间
    last_success_time: float = 0    # 上次成功时间
    cooldown_until: float = 0       # 冷却截止时间（降级后暂不使用）

    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return 1.0 - (self.total_failures / self.total_calls)

    @property
    def available(self) -> bool:
        """是否可用（不在冷却中，健康分>0）"""
        return self.health > 0 and time.time() > self.cooldown_until

    @property
    def effective_priority(self) -> float:
        """有效优先级 = 基础优先级 × 健康分系数"""
        return self.priority * (self.health / 100.0)


class SourceRegistry:
    """
    数据源注册表
    为每类数据维护一组有序数据源，支持动态优先级调整
    """

    # 降级阈值：连续失败 N 次触发降级
    DOWNGRADE_THRESHOLD = 3
    # 降级幅度：优先级降低的百分比
    DOWNGRADE_RATIO = 0.5
    # 健康分扣减
    HEALTH_PENALTY = 30
    # 健康分恢复（每次成功）
    HEALTH_RECOVERY = 10
    # 恢复冷却：降级后 N 秒内不自动恢复
    RECOVERY_COOLDOWN = 300
    # 最低健康分
    MIN_HEALTH = 0
    # 最高健康分
    MAX_HEALTH = 100

    def __init__(self):
        self._sources: dict[str, list[SourceEntry]] = {}
        self._lock = threading.Lock()

    def register(self, data_type: str, source: SourceEntry):
        """注册数据源"""
        with self._lock:
            if data_type not in self._sources:
                self._sources[data_type] = []
            self._sources[data_type].append(source)
            # 按优先级降序排列
            self._sources[data_type].sort(key=lambda s: s.effective_priority, reverse=True)

    def get_sources(self, data_type: str) -> list[SourceEntry]:
        """获取某类数据的所有可用源（按有效优先级排序）"""
        with self._lock:
            sources = self._sources.get(data_type, [])
            # 按有效优先级排序，可用的排前面
            available = [s for s in sources if s.available]
            unavailable = [s for s in sources if not s.available]
            available.sort(key=lambda s: s.effective_priority, reverse=True)
            return available + unavailable

    def record_success(self, source: SourceEntry):
        """记录成功"""
        with self._lock:
            source.total_calls += 1
            source.consecutive_failures = 0
            source.last_success_time = time.time()

            # 恢复健康分
            old_health = source.health
            source.health = min(self.MAX_HEALTH, source.health + self.HEALTH_RECOVERY)

            if source.health != old_health:
                logger.debug(
                    f"[Registry] {source.name} 成功, 健康分 {old_health}→{source.health}"
                )

    def record_failure(self, source: SourceEntry, error: str = ""):
        """记录失败，连续失败≥阈值时触发降级"""
        with self._lock:
            source.total_calls += 1
            source.total_failures += 1
            source.consecutive_failures += 1
            source.last_failure_time = time.time()

            old_health = source.health
            old_priority = source.priority

            # 扣减健康分
            source.health = max(self.MIN_HEALTH, source.health - self.HEALTH_PENALTY)

            # 连续失败达阈值 → 降级
            if source.consecutive_failures >= self.DOWNGRADE_THRESHOLD:
                source.priority = max(1, int(source.priority * (1 - self.DOWNGRADE_RATIO)))
                source.cooldown_until = time.time() + self.RECOVERY_COOLDOWN
                logger.warning(
                    f"[Registry] ⚠️ {source.name} 连续失败{source.consecutive_failures}次, "
                    f"降级: 优先级 {old_priority}→{source.priority}, "
                    f"健康分 {old_health}→{source.health}, "
                    f"冷却{self.RECOVERY_COOLDOWN}s. 错误: {error}"
                )

                # 自动提升同组其他源的优先级
                self._boost_others(source)
            else:
                logger.info(
                    f"[Registry] {source.name} 失败({source.consecutive_failures}/"
                    f"{self.DOWNGRADE_THRESHOLD}), 健康分 {old_health}→{source.health}. "
                    f"错误: {error}"
                )

    def _boost_others(self, failed_source: SourceEntry):
        """降级一个源后，提升同组其他可用源的优先级"""
        for data_type, sources in self._sources.items():
            for s in sources:
                if s is failed_source:
                    continue
                if s.name == failed_source.name:
                    # 同名源在其他数据类型中也降级
                    s.priority = max(1, int(s.priority * (1 - self.DOWNGRADE_RATIO)))
                    s.health = max(self.MIN_HEALTH, s.health - self.HEALTH_PENALTY)

    def recover_all(self):
        """定期恢复所有源的健康分（定时任务调用）"""
        with self._lock:
            now = time.time()
            for sources in self._sources.values():
                for s in sources:
                    if now > s.cooldown_until and s.health < self.MAX_HEALTH:
                        s.health = min(self.MAX_HEALTH, s.health + 5)
                    # 重置连续失败计数（超过冷却期后）
                    if now - s.last_failure_time > self.RECOVERY_COOLDOWN:
                        s.consecutive_failures = 0

    def get_status(self) -> dict:
        """获取所有数据源状态"""
        with self._lock:
            status = {}
            for data_type, sources in self._sources.items():
                status[data_type] = []
                for s in sources:
                    status[data_type].append({
                        "name": s.name,
                        "priority": s.priority,
                        "health": s.health,
                        "effective_priority": round(s.effective_priority, 1),
                        "consecutive_failures": s.consecutive_failures,
                        "total_calls": s.total_calls,
                        "success_rate": f"{s.success_rate:.1%}",
                        "available": s.available,
                        "last_success": datetime.fromtimestamp(s.last_success_time).strftime("%H:%M:%S") if s.last_success_time else "-",
                        "last_failure": datetime.fromtimestamp(s.last_failure_time).strftime("%H:%M:%S") if s.last_failure_time else "-",
                    })
            return status

    def force_reset(self, data_type: str = None):
        """手动重置优先级和健康分"""
        with self._lock:
            targets = [data_type] if data_type else list(self._sources.keys())
            for dt in targets:
                for s in self._sources.get(dt, []):
                    s.health = self.MAX_HEALTH
                    s.consecutive_failures = 0
                    s.cooldown_until = 0
            logger.info(f"[Registry] 已重置: {targets}")


# 全局注册表
_registry = SourceRegistry()


def _try_sources(data_type: str, cache_key: str, cache, ttl: int,
                 stale_fallback: bool = False) -> Optional[list]:
    """
    通用多源获取逻辑：
    1. 查缓存
    2. 按有效优先级尝试各源
    3. 成功→记录+写缓存  失败→降级+尝试下一个
    4. 全部失败→返回过期缓存(核心数据) 或 None
    """
    # 1. 缓存
    cached = cache.get(cache_key, ttl)
    if cached is not None:
        return cached

    # 2. 尝试数据源
    sources = _registry.get_sources(data_type)
    last_error = None

    for source in sources:
        if not source.available:
            continue

        polite_delay()
        try:
            result = source.fetch_fn()
            if result is None or (isinstance(result, pd.DataFrame) and result.empty):
                raise ValueError(f"{source.name} 返回空数据")

            # 成功
            _registry.record_success(source)
            records = _to_records(result) if isinstance(result, pd.DataFrame) else result
            if records:
                cache.set(cache_key, records)
            return records

        except Exception as e:
            last_error = str(e)
            _registry.record_failure(source, last_error)
            continue

    # 3. 全部失败
    logger.error(f"[Fetcher] {data_type} 所有源均失败")

    # 4. 降级：返回过期缓存
    if stale_fallback:
        stale = cache.get_stale(cache_key)
        if stale is not None:
            logger.info(f"[Fetcher] {data_type} 使用过期缓存降级")
            return stale

    return None


# =============================================================================
# 磁盘缓存
# =============================================================================
class DiskCache:
    """基于 JSON 文件的磁盘缓存"""

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
        path = self._key_to_path(key)
        record = {"key": key, "timestamp": time.time(), "data": data}
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(record, f, ensure_ascii=False, default=str)
        except IOError as e:
            logger.error(f"[Cache] 写入失败: {e}")

    def cleanup(self):
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
    time.sleep(random.uniform(0.5, 2.0))


def random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }


def _to_records(df: pd.DataFrame) -> list:
    return df.replace({np.nan: None}).to_dict(orient="records")


# =============================================================================
# TTL 策略
# =============================================================================
def _market_ttl() -> int:
    now = datetime.now()
    if now.weekday() >= 5:
        return 86400
    if 9 <= now.hour < 16:
        return 60
    return 300


# =============================================================================
# 数据源实现
# =============================================================================
class SinaAPI:
    """新浪财经 HTTP 接口"""

    HQ_URL = "https://hq.sinajs.cn/list="
    KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"

    @staticmethod
    def get_realtime(codes: list) -> list:
        if not codes:
            return []
        sina_codes = []
        for c in codes[:80]:
            c = str(c).strip()
            prefix = "sh" if c.startswith("6") else "sz"
            sina_codes.append(f"{prefix}{c}")
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

    @staticmethod
    def get_kline(code: str, scale: str = "240", datalen: int = 60) -> list:
        market = "sh" if code.startswith("6") else "sz"
        resp = requests.get(
            SinaAPI.KLINE_URL,
            params={"symbol": f"{market}{code}", "scale": scale, "ma": "no", "datalen": datalen},
            headers=random_headers(), timeout=10,
        )
        data = resp.json()
        return data if isinstance(data, list) else []


class TencentAPI:
    """腾讯财经 HTTP 接口 — 第三备用源"""

    KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    @staticmethod
    def get_kline(code: str, period: str = "day", count: int = 60) -> list:
        market = "sh" if code.startswith("6") else "sz"
        param = f"{market}{code}"
        resp = requests.get(
            TencentAPI.KLINE_URL,
            params={"param": param, "type": period, "count": count},
            headers=random_headers(), timeout=10,
        )
        data = resp.json()
        try:
            stock_data = data.get("data", {}).get(param, {})
            klines = stock_data.get("day" if period == "day" else f"qfq{period}", [])
            records = []
            for k in klines:
                if len(k) >= 6:
                    records.append({
                        "日期": k[0], "开盘": float(k[1]), "收盘": float(k[2]),
                        "最高": float(k[3]), "最低": float(k[4]),
                        "成交量": int(k[5] or 0), "成交额": 0,
                        "涨跌幅": 0, "涨跌额": 0, "振幅": 0, "换手率": 0,
                    })
            return records
        except (KeyError, IndexError, ValueError):
            return []

    @staticmethod
    def get_minute_kline(code: str, period: str = "5") -> list:
        market = "sh" if code.startswith("6") else "sz"
        param = f"{market}{code}"
        try:
            resp = requests.get(
                f"https://web.ifzq.gtimg.cn/appstock/app/minute/query",
                params={"code": param},
                headers=random_headers(), timeout=10,
            )
            data = resp.json()
            items = data.get("data", {}).get(param, {}).get("data", [])
            records = []
            for item in items:
                parts = item.split(" ")
                if len(parts) >= 6:
                    records.append({
                        "时间": parts[0], "开盘": float(parts[1]), "收盘": float(parts[2]),
                        "最高": float(parts[3]), "最低": float(parts[4]),
                        "成交量": int(parts[5] or 0), "成交额": 0,
                    })
            return records
        except Exception:
            return []


# =============================================================================
# 主数据获取器
# =============================================================================
class DataFetcher:
    """
    A股数据获取器 v3
    基于 SourceRegistry 的自适应多源架构
    """

    def __init__(self):
        self.cache = DiskCache(max_age_days=30)
        self.cache.cleanup()
        self.registry = _registry
        self._register_sources()
        logger.info("[Fetcher] 数据源注册完成")

    def _register_sources(self):
        """注册所有数据源及其获取函数"""

        # ── 涨停池（核心数据，仅东方财富）───────────────────
        self.registry.register("zt_pool", SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda: ak.stock_zt_pool_em(
                date=datetime.now().strftime("%Y%m%d")
            ),
            priority=100,
        ))

        # ── 炸板池（核心数据，仅东方财富）───────────────────
        self.registry.register("zr_pool", SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda: ak.stock_zt_pool_zbgc_em(
                date=datetime.now().strftime("%Y%m%d")
            ),
            priority=100,
        ))

        # ── 实时行情（通用数据，多源）────────────────────────
        self.registry.register("realtime", SourceEntry(
            name="efinance",
            fetch_fn=lambda: ef.stock.get_realtime_quotes(),
            priority=100,
        ))
        # 新浪需要代码列表，无法全量获取，作为低优先级补充

        # ── 分钟K线（通用数据，多源）────────────────────────
        # 动态注册：需要 code 参数，这里注册模板，实际调用时按 code 创建

        # ── 日线K线（通用数据，多源）────────────────────────
        # 同上，动态注册

        # ── 板块排名（核心数据，仅东方财富）─────────────────
        self.registry.register("board_concept", SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda: ak.stock_board_concept_name_em(),
            priority=100,
        ))
        self.registry.register("board_industry", SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda: ak.stock_board_industry_name_em(),
            priority=100,
        ))

        # ── 资金流向（核心数据，仅东方财富）─────────────────
        # 动态注册，需要 code 参数

        # ── 龙虎榜（核心数据，仅东方财富）───────────────────
        self.registry.register("lhb", SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda: ak.stock_lhb_detail_em(
                start_date=datetime.now().strftime("%Y%m%d"),
                end_date=datetime.now().strftime("%Y%m%d"),
            ),
            priority=100,
        ))

    # =========================================================================
    # 核心数据获取（仅东方财富 + 过期缓存降级）
    # =========================================================================
    def get_zt_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """涨停池"""
        date_str = trade_date or datetime.now().strftime("%Y%m%d")
        key = f"zt_pool_{date_str}"
        ttl = _market_ttl()

        # 如果指定了日期，注册临时源
        if trade_date:
            self.registry.register("zt_pool_date", SourceEntry(
                name=f"akshare_EM_{date_str}",
                fetch_fn=lambda d=date_str: ak.stock_zt_pool_em(date=d),
                priority=100,
            ))
            data = _try_sources("zt_pool_date", key, self.cache, ttl, stale_fallback=True)
        else:
            data = _try_sources("zt_pool", key, self.cache, ttl, stale_fallback=True)

        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    def get_lb_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """连板池（从涨停池筛选）"""
        zt = self.get_zt_pool(trade_date)
        if zt.empty or "连板数" not in zt.columns:
            return pd.DataFrame()
        return zt[zt["连板数"] > 1].copy()

    def get_zr_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """炸板池"""
        date_str = trade_date or datetime.now().strftime("%Y%m%d")
        key = f"zr_pool_{date_str}"
        ttl = _market_ttl()

        if trade_date:
            self.registry.register("zr_pool_date", SourceEntry(
                name=f"akshare_EM_{date_str}",
                fetch_fn=lambda d=date_str: ak.stock_zt_pool_zbgc_em(date=d),
                priority=100,
            ))
            data = _try_sources("zr_pool_date", key, self.cache, ttl, stale_fallback=True)
        else:
            data = _try_sources("zr_pool", key, self.cache, ttl, stale_fallback=True)

        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    # =========================================================================
    # 通用数据获取（多源回退）
    # =========================================================================
    def get_realtime_quotes(self) -> pd.DataFrame:
        """全市场实时行情"""
        key = "realtime_quotes"
        ttl = 10
        data = _try_sources("realtime", key, self.cache, ttl)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    def get_minute_kline(self, code: str, period: str = "5") -> pd.DataFrame:
        """分钟K线 — akshare → 新浪 → 腾讯"""
        key = f"min_kline_{code}_{period}"
        ttl = 3600

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        # 动态注册该 code 的源
        src_type = f"min_kline_{code}_{period}"

        # 源1: akshare
        self.registry.register(src_type, SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda c=code, p=period: ak.stock_zh_a_hist_min_em(
                symbol=c, period=p, adjust="qfq"
            ),
            priority=100,
        ))

        # 源2: 新浪
        self.registry.register(src_type, SourceEntry(
            name="sina",
            fetch_fn=lambda c=code, p=period: pd.DataFrame(
                [{"时间": d.get("day", ""), "开盘": float(d.get("open", 0)),
                  "收盘": float(d.get("close", 0)), "最高": float(d.get("high", 0)),
                  "最低": float(d.get("low", 0)), "成交量": int(d.get("volume", 0)),
                  "成交额": 0} for d in SinaAPI.get_kline(c, scale=p, datalen=240)]
            ),
            priority=50,
        ))

        # 源3: 腾讯
        self.registry.register(src_type, SourceEntry(
            name="tencent",
            fetch_fn=lambda c=code, p=period: pd.DataFrame(
                TencentAPI.get_minute_kline(c, period=p)
            ),
            priority=25,
        ))

        data = _try_sources(src_type, key, self.cache, ttl)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    def get_stock_history(self, code: str, period: str = "daily",
                          start_date: str = None, end_date: str = None,
                          days: int = 30) -> pd.DataFrame:
        """日线K线 — akshare → 新浪 → 腾讯"""
        if not end_date:
            end_date = datetime.now().strftime("%Y%m%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

        key = f"hist_{code}_{period}_{start_date}_{end_date}"
        ttl = 86400

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        src_type = f"hist_{code}"

        # 源1: akshare
        self.registry.register(src_type, SourceEntry(
            name="akshare_EM",
            fetch_fn=lambda c=code, s=start_date, e=end_date: ak.stock_zh_a_hist(
                symbol=c, period=period, start_date=s, end_date=e, adjust="qfq"
            ),
            priority=100,
        ))

        # 源2: 新浪
        self.registry.register(src_type, SourceEntry(
            name="sina",
            fetch_fn=lambda c=code, d=days: pd.DataFrame([
                {"日期": item.get("day", ""), "开盘": float(item.get("open", 0)),
                 "收盘": float(item.get("close", 0)), "最高": float(item.get("high", 0)),
                 "最低": float(item.get("low", 0)), "成交量": int(item.get("volume", 0)),
                 "成交额": 0, "振幅": 0,
                 "涨跌幅": round((float(item.get("close", 0)) - float(item.get("open", 0)))
                                 / float(item.get("open", 1)) * 100, 2),
                 "涨跌额": round(float(item.get("close", 0)) - float(item.get("open", 0)), 2),
                 "换手率": 0}
                for item in SinaAPI.get_kline(c, scale="240", datalen=d)
            ]),
            priority=50,
        ))

        # 源3: 腾讯
        self.registry.register(src_type, SourceEntry(
            name="tencent",
            fetch_fn=lambda c=code, d=days: pd.DataFrame(
                TencentAPI.get_kline(c, period="day", count=d)
            ),
            priority=25,
        ))

        data = _try_sources(src_type, key, self.cache, ttl)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    # =========================================================================
    # 板块数据（核心数据，仅东方财富）
    # =========================================================================
    def get_board_list(self, board_type: str = "概念板块") -> pd.DataFrame:
        key = f"board_{board_type}"
        ttl = 120
        src = "board_concept" if board_type == "概念板块" else "board_industry"
        data = _try_sources(src, key, self.cache, ttl, stale_fallback=True)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    def get_board_stocks(self, board_name: str) -> pd.DataFrame:
        key = f"board_cons_{board_name}"
        ttl = 300

        cached = self.cache.get(key, ttl)
        if cached is not None:
            return pd.DataFrame(cached)

        polite_delay()
        try:
            df = ak.stock_board_concept_cons_em(symbol=board_name)
            if not df.empty:
                self.cache.set(key, _to_records(df))
            return df
        except Exception as e:
            logger.error(f"[EM] 板块成分股失败({board_name}): {e}")
            return pd.DataFrame()

    # =========================================================================
    # 资金流向 / 龙虎榜
    # =========================================================================
    def get_fund_flow_individual(self, code: str) -> pd.DataFrame:
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
                self.cache.set(key, _to_records(df))
            return df
        except Exception as e:
            logger.error(f"[EM] 资金流向失败({code}): {e}")
            return pd.DataFrame()

    def get_lhb_data(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        if not trade_date:
            trade_date = datetime.now().strftime("%Y%m%d")
        key = f"lhb_{trade_date}"
        ttl = 86400
        data = _try_sources("lhb", key, self.cache, ttl, stale_fallback=True)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()

    # =========================================================================
    # 管理接口
    # =========================================================================
    def get_source_status(self) -> dict:
        """获取所有数据源健康状态"""
        return self.registry.get_status()

    def reset_source_priorities(self, data_type: str = None):
        """手动重置数据源优先级"""
        self.registry.force_reset(data_type)

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
