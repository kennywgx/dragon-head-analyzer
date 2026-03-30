"""
龙头分析引擎 - 核心规则执行
不做预判，不提示风险，纯规则机械执行
"""
import pandas as pd
from datetime import datetime
from typing import Optional
from ..core.config import RULES
from .data_fetcher import DataFetcher
from .logger import AnalyzerLogger


class DragonHeadAnalyzer:
    """龙头战法分析器"""

    def __init__(self, fetcher: DataFetcher, logger: AnalyzerLogger):
        self.fetcher = fetcher
        self.logger = logger
        self.rules = RULES

    def scan_all(self) -> dict:
        """全量扫描：涨停池 → 龙头识别 → 信号判定"""
        today = datetime.now().strftime("%Y%m%d")
        self.logger.log(f"========== 开始全量扫描 {today} ==========")

        # Step 1: 获取涨停池
        zt_pool = self.fetcher.get_zt_pool()
        if zt_pool.empty:
            self.logger.log("涨停池为空，今日无涨停数据")
            return {"date": today, "candidates": [], "signals": []}

        self.logger.log(f"涨停池共 {len(zt_pool)} 只")

        # Step 2: 获取连板池
        lb_pool = self.fetcher.get_lb_pool()
        self.logger.log(f"连板池共 {len(lb_pool) if not lb_pool.empty else 0} 只")

        # Step 3: 获取炸板池
        zr_pool = self.fetcher.get_zr_pool()
        self.logger.log(f"炸板池共 {len(zr_pool) if not zr_pool.empty else 0} 只")

        # Step 4: 识别龙头候选
        candidates = self._identify_candidates(zt_pool, lb_pool)
        self.logger.log(f"龙头候选 {len(candidates)} 只")

        # Step 5: 生成交易信号
        signals = self._generate_signals(candidates, zt_pool, zr_pool)

        result = {
            "date": today,
            "zt_pool_count": len(zt_pool),
            "lb_pool_count": len(lb_pool) if not lb_pool.empty else 0,
            "zr_pool_count": len(zr_pool) if not zr_pool.empty else 0,
            "candidates": candidates,
            "signals": signals,
        }

        self.logger.log(f"扫描完成：候选 {len(candidates)} 只，信号 {len(signals)} 条")
        self.logger.log("=" * 50)
        return result

    def _identify_candidates(self, zt_pool: pd.DataFrame,
                              lb_pool: pd.DataFrame) -> list:
        """
        Step 1: 龙头候选识别
        规则：连板高度 >= min_lianban_count
        """
        candidates = []

        if zt_pool.empty:
            return candidates

        # 从涨停池中筛选连板股
        for _, row in zt_pool.iterrows():
            stock = self._row_to_dict(row)
            lianban = stock.get("连板数", 0)

            if lianban >= self.rules["min_lianban_count"]:
                # 计算封板评分
                score = self._calc_seal_score(stock, lianban)
                stock["seal_score"] = score
                stock["level"] = self._get_level(lianban)
                candidates.append(stock)

        # 按连板数降序，同连板数按封板评分降序
        candidates.sort(key=lambda x: (x.get("连板数", 0), x["seal_score"]), reverse=True)
        return candidates

    def _calc_seal_score(self, stock: dict, lianban: int) -> float:
        """
        计算封板评分
        因素：连板数 + 封单额占比 + 涨幅
        """
        score = 0.0

        # 连板高度分（每板10分）
        score += lianban * 10

        # 封单额占比（如果有数据）
        seal_amount = stock.get("封单额", 0) or 0
        circ_mv = stock.get("流通市值", 0) or 0
        if circ_mv > 0 and seal_amount > 0:
            ratio = seal_amount / circ_mv
            if ratio >= self.rules["seal_order_ratio_threshold"]:
                score += 15
            elif ratio >= self.rules["seal_order_ratio_threshold"] * 0.5:
                score += 8

        # 涨幅（涨停=10分，其余按比例）
        pct_chg = stock.get("涨跌幅", 0) or 0
        if pct_chg >= 9.9:
            score += 10
        elif pct_chg >= 5:
            score += 5

        return round(score, 1)

    def _get_level(self, lianban: int) -> str:
        """根据连板数定级"""
        if lianban >= 7:
            return "妖王"
        elif lianban >= 5:
            return "总龙头"
        elif lianban >= 3:
            return "分支龙头"
        else:
            return "跟风龙头"

    def _generate_signals(self, candidates: list, zt_pool: pd.DataFrame,
                           zr_pool: pd.DataFrame) -> list:
        """
        Step 2: 生成交易信号
        当前阶段只做识别，信号类型：
        - 龙头确认：连板股满足龙头条件
        - 高位预警：连板数过高
        - 断板预警：前日涨停今日未进涨停池
        """
        signals = []
        now = datetime.now().strftime("%H:%M:%S")

        for c in candidates:
            lianban = c.get("连板数", 0)

            # 龙头确认信号
            signals.append({
                "time": now,
                "code": c.get("代码", ""),
                "name": c.get("名称", ""),
                "type": "龙头确认",
                "detail": f"{lianban}连板 | {c.get('level', '')} | 封板评分: {c.get('seal_score', 0)}",
                "lianban": lianban,
                "level": c.get("level", ""),
                "score": c.get("seal_score", 0),
            })

            # 高位预警（连板>=5）
            if lianban >= 5:
                signals.append({
                    "time": now,
                    "code": c.get("代码", ""),
                    "name": c.get("名称", ""),
                    "type": "高位连板",
                    "detail": f"已达{lianban}连板",
                    "lianban": lianban,
                })

        return signals

    def _row_to_dict(self, row) -> dict:
        """DataFrame行转字典，处理NaN"""
        d = {}
        for col in row.index:
            val = row[col]
            if pd.isna(val):
                d[col] = None
            else:
                d[col] = val
        return d

    def get_stock_detail(self, code: str) -> dict:
        """获取个股详情（分时+资金流+连板信息）"""
        detail = {"code": code}

        # 分时K线（5分钟）
        min_kline = self.fetcher.get_minute_kline(code, period="5")
        if not min_kline.empty:
            detail["minute_kline"] = min_kline.tail(48).to_dict(orient="records")

        # 日线
        hist = self.fetcher.get_stock_history(code, start_date="20250101")
        if not hist.empty:
            detail["daily_kline"] = hist.tail(60).to_dict(orient="records")

        # 资金流向
        fund_flow = self.fetcher.get_fund_flow_individual(code)
        if not fund_flow.empty:
            detail["fund_flow"] = fund_flow.tail(5).to_dict(orient="records")

        return detail
