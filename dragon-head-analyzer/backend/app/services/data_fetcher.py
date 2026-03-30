"""
数据获取服务 - AKShare + efinance
"""
import akshare as ak
import efinance as ef
import pandas as pd
from datetime import datetime, date
from typing import Optional
import traceback


class DataFetcher:
    """A股数据获取器"""

    def __init__(self):
        self._cache = {}
        self._cache_time = {}

    def _is_cache_valid(self, key: str, ttl: int = 60) -> bool:
        """检查缓存是否有效（默认60秒）"""
        if key not in self._cache_time:
            return False
        elapsed = (datetime.now() - self._cache_time[key]).total_seconds()
        return elapsed < ttl

    def get_zt_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取涨停股池（东财）
        包含：代码、名称、连板数、封单额、流通市值、成交额等
        """
        cache_key = f"zt_pool_{trade_date}"
        if self._is_cache_valid(cache_key, ttl=30):
            return self._cache[cache_key]

        try:
            if trade_date:
                df = ak.stock_zt_pool_em(date=trade_date)
            else:
                df = ak.stock_zt_pool_em(date=datetime.now().strftime("%Y%m%d"))
            self._cache[cache_key] = df
            self._cache_time[cache_key] = datetime.now()
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取涨停池失败: {e}")
            traceback.print_exc()
            return pd.DataFrame()

    def get_lb_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取连板股池（从涨停池筛选连板数>1）
        akshare新版无独立连板池接口，从涨停池中筛选
        """
        try:
            zt = self.get_zt_pool(trade_date)
            if zt.empty:
                return pd.DataFrame()
            if '连板数' in zt.columns:
                return zt[zt['连板数'] > 1].copy()
            return pd.DataFrame()
        except Exception as e:
            print(f"[DataFetcher] 获取连板池失败: {e}")
            traceback.print_exc()
            return pd.DataFrame()

    def get_zr_pool(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """获取炸板股池"""
        try:
            if trade_date:
                df = ak.stock_zt_pool_zbgc_em(date=trade_date)
            else:
                df = ak.stock_zt_pool_zbgc_em(date=datetime.now().strftime("%Y%m%d"))
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取炸板池失败: {e}")
            traceback.print_exc()
            return pd.DataFrame()

    def get_realtime_quotes(self) -> pd.DataFrame:
        """
        获取全市场实时行情快照（efinance，速度快）
        """
        cache_key = "realtime_quotes"
        if self._is_cache_valid(cache_key, ttl=10):
            return self._cache[cache_key]

        try:
            df = ef.stock.get_realtime_quotes()
            self._cache[cache_key] = df
            self._cache_time[cache_key] = datetime.now()
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取实时行情失败: {e}")
            traceback.print_exc()
            return pd.DataFrame()

    def get_minute_kline(self, code: str, period: str = "1") -> pd.DataFrame:
        """
        获取分时K线
        period: 1/5/15/30/60 分钟
        """
        try:
            df = ak.stock_zh_a_hist_min_em(
                symbol=code, period=period, adjust="qfq"
            )
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取分时K线失败({code}): {e}")
            return pd.DataFrame()

    def get_stock_history(self, code: str, period: str = "daily",
                          start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取日线/周线历史数据"""
        try:
            if not end_date:
                end_date = datetime.now().strftime("%Y%m%d")
            if not start_date:
                start_date = "20240101"
            df = ak.stock_zh_a_hist(
                symbol=code, period=period,
                start_date=start_date, end_date=end_date, adjust="qfq"
            )
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取历史数据失败({code}): {e}")
            return pd.DataFrame()

    def get_board_list(self, board_type: str = "概念板块") -> pd.DataFrame:
        """
        获取板块列表及涨幅排名
        board_type: "概念板块" / "行业板块"
        """
        cache_key = f"board_{board_type}"
        if self._is_cache_valid(cache_key, ttl=60):
            return self._cache[cache_key]

        try:
            if board_type == "概念板块":
                df = ak.stock_board_concept_name_em()
            else:
                df = ak.stock_board_industry_name_em()
            self._cache[cache_key] = df
            self._cache_time[cache_key] = datetime.now()
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取板块列表失败: {e}")
            return pd.DataFrame()

    def get_board_stocks(self, board_name: str) -> pd.DataFrame:
        """获取板块成分股"""
        try:
            df = ak.stock_board_concept_cons_em(symbol=board_name)
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取板块成分股失败({board_name}): {e}")
            return pd.DataFrame()

    def get_fund_flow_individual(self, code: str) -> pd.DataFrame:
        """获取个股资金流向"""
        try:
            market = "sh" if code.startswith("6") else "sz"
            df = ak.stock_individual_fund_flow(stock=code, market=market)
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取资金流向失败({code}): {e}")
            return pd.DataFrame()

    def get_lhb_data(self, trade_date: Optional[str] = None) -> pd.DataFrame:
        """获取龙虎榜数据"""
        try:
            if not trade_date:
                trade_date = datetime.now().strftime("%Y%m%d")
            df = ak.stock_lhb_detail_em(start_date=trade_date, end_date=trade_date)
            return df
        except Exception as e:
            print(f"[DataFetcher] 获取龙虎榜失败: {e}")
            return pd.DataFrame()
