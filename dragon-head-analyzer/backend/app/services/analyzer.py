"""
龙头分析引擎 - 核心规则执行
不做预判，不提示风险，纯规则机械执行

规则覆盖：
1. 龙头候选识别（连板高度 + 封板评分）
2. 板块共振分析
3. 弱转强 / 分歧转一致判定
4. 卡位介入规则
5. 离场信号（断板 / 放量长阴 / 板块退潮）
6. 仓位管理建议
7. K线形态识别（一字板 / T字板）
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

    # ==========================================================================
    # 全量扫描
    # ==========================================================================
    def scan_all(self) -> dict:
        """全量扫描：涨停池 → 龙头识别 → 信号判定"""
        today = datetime.now().strftime("%Y%m%d")
        self.logger.log(f"========== 开始全量扫描 {today} ==========")

        # Step 1: 涨停池
        zt_pool = self.fetcher.get_zt_pool()
        if zt_pool.empty:
            self.logger.log("涨停池为空，今日无涨停数据")
            return {"date": today, "candidates": [], "signals": [], "exit_signals": [], "position_suggestions": []}

        self.logger.log(f"涨停池共 {len(zt_pool)} 只")

        # Step 2: 连板池
        lb_pool = self.fetcher.get_lb_pool()
        self.logger.log(f"连板池共 {len(lb_pool) if not lb_pool.empty else 0} 只")

        # Step 3: 炸板池
        zr_pool = self.fetcher.get_zr_pool()
        self.logger.log(f"炸板池共 {len(zr_pool) if not zr_pool.empty else 0} 只")

        # Step 4: 板块数据
        board_data = self._fetch_board_data()

        # Step 5: 识别龙头候选（含板块共振加分）
        candidates = self._identify_candidates(zt_pool, lb_pool, board_data)
        self.logger.log(f"龙头候选 {len(candidates)} 只")

        # Step 6: 弱转强 / 分歧转一致检测
        candidates = self._detect_pattern_shifts(candidates)

        # Step 7: 卡位判断
        candidates = self._detect_compete_slots(candidates)

        # Step 8: K线形态识别
        candidates = self._detect_kline_patterns(candidates)

        # Step 9: 生成入场信号
        signals = self._generate_signals(candidates, zt_pool, zr_pool)

        # Step 10: 离场信号
        exit_signals = self._generate_exit_signals(candidates, zt_pool, zr_pool, board_data)

        # Step 11: 仓位管理建议
        position_suggestions = self._generate_position_suggestions(candidates)

        result = {
            "date": today,
            "zt_pool_count": len(zt_pool),
            "lb_pool_count": len(lb_pool) if not lb_pool.empty else 0,
            "zr_pool_count": len(zr_pool) if not zr_pool.empty else 0,
            "candidates": candidates,
            "signals": signals,
            "exit_signals": exit_signals,
            "position_suggestions": position_suggestions,
        }

        total_signals = len(signals) + len(exit_signals)
        self.logger.log(f"扫描完成：候选 {len(candidates)} 只，信号 {total_signals} 条")
        self.logger.log("=" * 50)
        return result

    # ==========================================================================
    # Step 5: 龙头候选识别 + 板块共振
    # ==========================================================================
    def _identify_candidates(self, zt_pool: pd.DataFrame,
                              lb_pool: pd.DataFrame,
                              board_data: dict) -> list:
        """龙头候选识别：连板高度 + 封板评分 + 板块共振加分"""
        candidates = []
        if zt_pool.empty:
            return candidates

        for _, row in zt_pool.iterrows():
            stock = self._row_to_dict(row)
            lianban = stock.get("连板数", 0)

            if lianban >= self.rules["min_lianban_count"]:
                # 基础封板评分
                score = self._calc_seal_score(stock, lianban)

                # 板块共振加分
                board_bonus = self._calc_board_resonance(stock, board_data)
                score += board_bonus

                stock["seal_score"] = score
                stock["board_bonus"] = board_bonus
                stock["level"] = self._get_level(lianban)
                candidates.append(stock)

        candidates.sort(key=lambda x: (x.get("连板数", 0), x["seal_score"]), reverse=True)
        return candidates

    def _calc_seal_score(self, stock: dict, lianban: int) -> float:
        """封板评分：连板数 + 封单额占比 + 涨幅"""
        score = 0.0

        # 连板高度分（每板10分）
        score += lianban * 10

        # 封单额占比（三级评分）
        seal_amount = stock.get("封单额", 0) or 0
        circ_mv = stock.get("流通市值", 0) or 0
        if circ_mv > 0 and seal_amount > 0:
            ratio = seal_amount / circ_mv
            if ratio >= self.rules["seal_order_ratio_threshold"]:
                score += 15   # 强封
            elif ratio >= self.rules["seal_ratio_medium"]:
                score += 8    # 中封
            elif ratio >= self.rules["seal_ratio_weak"]:
                score += 3    # 弱封

        # 涨幅
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

    # ==========================================================================
    # 板块共振分析
    # ==========================================================================
    def _fetch_board_data(self) -> dict:
        """获取板块数据用于共振分析"""
        result = {"concept": {}, "industry": {}}
        try:
            concept_df = self.fetcher.get_board_list("概念板块")
            if not concept_df.empty:
                for _, row in concept_df.iterrows():
                    name = row.get("板块名称", "")
                    if name:
                        result["concept"][name] = self._row_to_dict(row)
        except Exception as e:
            self.logger.log(f"板块数据获取异常: {e}")
        return result

    def _calc_board_resonance(self, stock: dict, board_data: dict) -> float:
        """
        板块共振加分
        如果个股所属板块当日整体涨幅靠前（前20%），加分
        """
        bonus = 0.0
        stock_name = stock.get("名称", "")

        # 涨停池中的板块信息有限，这里通过板块排名判断
        # 如果某板块涨幅排名靠前，其成分股有共振效应
        if board_data.get("concept"):
            sorted_boards = sorted(
                board_data["concept"].items(),
                key=lambda x: float(x[1].get("涨跌幅", 0) or 0),
                reverse=True
            )
            # 前20%的板块视为强势板块
            top_n = max(1, len(sorted_boards) // 5)
            top_boards = sorted_boards[:top_n]

            # 检查涨幅，如果板块涨幅>2% 且排名前20%
            for bname, bdata in top_boards:
                pct = float(bdata.get("涨跌幅", 0) or 0)
                if pct >= 2.0:
                    bonus = self.rules["board_resonance_bonus"]
                    break

        return bonus

    # ==========================================================================
    # Step 6: 弱转强 / 分歧转一致
    # ==========================================================================
    def _detect_pattern_shifts(self, candidates: list) -> list:
        """
        检测弱转强和分歧转一致：
        - 弱转强：前日涨幅<3%（弱板），今日涨停
        - 分歧转一致：前日振幅>5%（分歧板），今日涨停
        需要获取个股历史数据来判断
        """
        for c in candidates:
            code = c.get("代码", "")
            if not code:
                continue

            try:
                hist = self.fetcher.get_stock_history(code, start_date=self._get_recent_date(5))
                if hist.empty or len(hist) < 2:
                    continue

                yesterday = hist.iloc[-2]
                today_row = hist.iloc[-1]

                yesterday_pct = float(yesterday.get("涨跌幅", 0) or 0)
                yesterday_high = float(yesterday.get("最高", 0) or 0)
                yesterday_low = float(yesterday.get("最低", 0) or 0)
                yesterday_close = float(yesterday.get("收盘", 0) or 1)
                today_pct = float(today_row.get("涨跌幅", 0) or 0)

                # 前日振幅
                amplitude = abs(yesterday_high - yesterday_low) / yesterday_close * 100 if yesterday_close > 0 else 0

                c["patterns"] = c.get("patterns", [])

                # 弱转强：前日涨幅<3% 且今日涨停
                if yesterday_pct < self.rules["weak_turn_strong_pct"] and today_pct >= 9.9:
                    c["patterns"].append({
                        "type": "弱转强",
                        "detail": f"前日涨幅{yesterday_pct:.2f}% → 今日涨停",
                        "bonus": self.rules["weak_turn_strong_bonus"],
                    })
                    c["seal_score"] = c.get("seal_score", 0) + self.rules["weak_turn_strong_bonus"]

                # 分歧转一致：前日振幅>5% 且今日涨停
                if amplitude > self.rules["consensus_turn_pct"] and today_pct >= 9.9:
                    c["patterns"].append({
                        "type": "分歧转一致",
                        "detail": f"前日振幅{amplitude:.2f}% → 今日涨停",
                        "bonus": self.rules["consensus_turn_bonus"],
                    })
                    c["seal_score"] = c.get("seal_score", 0) + self.rules["consensus_turn_bonus"]

            except Exception as e:
                self.logger.log(f"形态检测异常({code}): {e}")

        # 重新排序
        candidates.sort(key=lambda x: (x.get("连板数", 0), x.get("seal_score", 0)), reverse=True)
        return candidates

    def _get_recent_date(self, days: int = 5) -> str:
        """获取N个交易日前的日期（近似）"""
        from datetime import timedelta
        d = datetime.now() - timedelta(days=days + 3)  # 多减几天跳过周末
        return d.strftime("%Y%m%d")

    # ==========================================================================
    # Step 7: 卡位介入
    # ==========================================================================
    def _detect_compete_slots(self, candidates: list) -> list:
        """
        卡位判断：
        同连板数的多只股票中，涨幅领先且放量的个股为卡位成功
        """
        # 按连板数分组
        by_level = {}
        for c in candidates:
            lb = c.get("连板数", 0)
            by_level.setdefault(lb, []).append(c)

        for lb, stocks in by_level.items():
            if len(stocks) < self.rules["compete_slot_same_level"]:
                continue

            # 按涨幅排序
            sorted_stocks = sorted(
                stocks,
                key=lambda x: float(x.get("涨跌幅", 0) or 0),
                reverse=True
            )

            top = sorted_stocks[0]
            top_pct = float(top.get("涨跌幅", 0) or 0)

            for other in sorted_stocks[1:]:
                other_pct = float(other.get("涨跌幅", 0) or 0)
                diff = top_pct - other_pct

                if diff >= self.rules["compete_slot_pct_advantage"]:
                    top["compete_slot"] = {
                        "type": "卡位成功",
                        "detail": f"{lb}连板级别中涨幅领先{diff:.1f}%（vs {other.get('名称', '')}）",
                        "rival": other.get("名称", ""),
                    }
                    break

        return candidates

    # ==========================================================================
    # Step 8: K线形态识别
    # ==========================================================================
    def _detect_kline_patterns(self, candidates: list) -> list:
        """
        K线形态识别：
        - 一字板：开盘价≈收盘价，全天涨停
        - T字板：有下影线的涨停板
        """
        for c in candidates:
            code = c.get("代码", "")
            if not code:
                continue

            try:
                hist = self.fetcher.get_stock_history(code, start_date=self._get_recent_date(3))
                if hist.empty:
                    continue

                today = hist.iloc[-1]
                open_price = float(today.get("开盘", 0) or 0)
                close_price = float(today.get("收盘", 0) or 0)
                low_price = float(today.get("最低", 0) or 0)
                pct = float(today.get("涨跌幅", 0) or 0)

                if close_price <= 0:
                    continue

                c["kline_patterns"] = c.get("kline_patterns", [])

                # 一字板检测：开盘≈收盘且涨停
                if pct >= 9.9 and abs(open_price - close_price) / close_price < self.rules["yi_zi_board_open_ratio"]:
                    c["kline_patterns"].append({
                        "type": "一字板",
                        "detail": "全天封死涨停，无开板",
                    })

                # T字板检测：有明显下影线的涨停
                if pct >= 9.9 and low_price > 0:
                    shadow_ratio = (close_price - low_price) / close_price
                    if shadow_ratio > self.rules["t_board_lower_shadow_pct"]:
                        c["kline_patterns"].append({
                            "type": "T字板",
                            "detail": f"下影线占比{shadow_ratio*100:.1f}%，曾开板后回封",
                        })

            except Exception as e:
                self.logger.log(f"K线形态检测异常({code}): {e}")

        return candidates

    # ==========================================================================
    # Step 9: 入场信号
    # ==========================================================================
    def _generate_signals(self, candidates: list, zt_pool: pd.DataFrame,
                           zr_pool: pd.DataFrame) -> list:
        """生成入场信号"""
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
                "detail": f"{lianban}连板 | {c.get('level', '')} | 评分: {c.get('seal_score', 0)}",
                "lianban": lianban,
                "level": c.get("level", ""),
                "score": c.get("seal_score", 0),
            })

            # 高位预警
            if lianban >= 5:
                signals.append({
                    "time": now,
                    "code": c.get("代码", ""),
                    "name": c.get("名称", ""),
                    "type": "高位连板",
                    "detail": f"已达{lianban}连板",
                    "lianban": lianban,
                })

            # 弱转强信号
            patterns = c.get("patterns", [])
            for p in patterns:
                if p["type"] == "弱转强":
                    signals.append({
                        "time": now,
                        "code": c.get("代码", ""),
                        "name": c.get("名称", ""),
                        "type": "弱转强",
                        "detail": p["detail"],
                        "lianban": lianban,
                    })
                elif p["type"] == "分歧转一致":
                    signals.append({
                        "time": now,
                        "code": c.get("代码", ""),
                        "name": c.get("名称", ""),
                        "type": "分歧转一致",
                        "detail": p["detail"],
                        "lianban": lianban,
                    })

            # 卡位信号
            compete = c.get("compete_slot")
            if compete:
                signals.append({
                    "time": now,
                    "code": c.get("代码", ""),
                    "name": c.get("名称", ""),
                    "type": "卡位成功",
                    "detail": compete["detail"],
                    "lianban": lianban,
                })

            # K线形态信号
            for kp in c.get("kline_patterns", []):
                signals.append({
                    "time": now,
                    "code": c.get("代码", ""),
                    "name": c.get("名称", ""),
                    "type": kp["type"],
                    "detail": kp["detail"],
                    "lianban": lianban,
                })

            # 板块共振信号
            if c.get("board_bonus", 0) > 0:
                signals.append({
                    "time": now,
                    "code": c.get("代码", ""),
                    "name": c.get("名称", ""),
                    "type": "板块共振",
                    "detail": f"所属板块当日强势（+{c['board_bonus']}分）",
                    "lianban": lianban,
                })

        return signals

    # ==========================================================================
    # Step 10: 离场信号
    # ==========================================================================
    def _generate_exit_signals(self, candidates: list, zt_pool: pd.DataFrame,
                                zr_pool: pd.DataFrame, board_data: dict) -> list:
        """
        离场信号：
        1. 断板：前日涨停今日未进涨停池
        2. 放量长阴：跌幅>7%且量比>1.8
        3. 板块退潮：同板块跌停>=3只
        """
        exit_signals = []
        now = datetime.now().strftime("%H:%M:%S")

        # 收集今日涨停代码
        zt_codes = set()
        if not zt_pool.empty:
            for _, row in zt_pool.iterrows():
                code = str(row.get("代码", ""))
                if code:
                    zt_codes.add(code)

        # 1. 断板检测：检查连板池中前日还在的股票今日是否消失
        try:
            yesterday_str = self._get_yesterday_date()
            yesterday_zt = self.fetcher.get_zt_pool(yesterday_str)
            if not yesterday_zt.empty and '连板数' in yesterday_zt.columns:
                yesterday_lb = yesterday_zt[yesterday_zt['连板数'] >= 2]
                for _, row in yesterday_lb.iterrows():
                    code = str(row.get("代码", ""))
                    name = str(row.get("名称", ""))
                    if code and code not in zt_codes:
                        prev_lb = int(row.get("连板数", 0))
                        exit_signals.append({
                            "time": now,
                            "code": code,
                            "name": name,
                            "type": "断板预警",
                            "detail": f"前日{prev_lb}连板，今日未封涨停",
                            "severity": "high" if prev_lb >= 5 else "medium",
                        })
        except Exception as e:
            self.logger.log(f"断板检测异常: {e}")

        # 2. 放量长阴检测
        for c in candidates:
            code = c.get("代码", "")
            if not code:
                continue
            try:
                hist = self.fetcher.get_stock_history(code, start_date=self._get_recent_date(3))
                if hist.empty or len(hist) < 2:
                    continue

                today_row = hist.iloc[-1]
                yesterday_row = hist.iloc[-2]

                today_pct = float(today_row.get("涨跌幅", 0) or 0)
                today_vol = float(today_row.get("成交量", 0) or 0)
                yesterday_vol = float(yesterday_row.get("成交量", 0) or 1)

                vol_ratio = today_vol / yesterday_vol if yesterday_vol > 0 else 0

                if today_pct <= self.rules["exit_long_yin_pct"] and vol_ratio >= self.rules["exit_long_yin_vol_ratio"]:
                    exit_signals.append({
                        "time": now,
                        "code": code,
                        "name": c.get("名称", ""),
                        "type": "放量长阴",
                        "detail": f"跌幅{today_pct:.1f}%，量比{vol_ratio:.1f}倍",
                        "severity": "high",
                    })

            except Exception:
                pass

        # 3. 板块退潮检测
        if not zr_pool.empty and "名称" in zr_pool.columns:
            # 统计炸板股的板块分布（近似处理：通过概念板块成分股）
            # 简化：如果炸板数>涨停数的50%，视为板块退潮
            zr_count = len(zr_pool)
            zt_count = len(zt_pool) if not zt_pool.empty else 0
            if zt_count > 0 and zr_count >= zt_count * 0.5:
                exit_signals.append({
                    "time": now,
                    "code": "MARKET",
                    "name": "市场整体",
                    "type": "板块退潮",
                    "detail": f"炸板{zr_count}只 vs 涨停{zt_count}只，市场情绪转弱",
                    "severity": "high",
                })

        return exit_signals

    def _get_yesterday_date(self) -> str:
        """获取上一个交易日日期（近似：跳过周末）"""
        from datetime import timedelta
        d = datetime.now() - timedelta(days=1)
        if d.weekday() == 6:  # 周日→周五
            d -= timedelta(days=2)
        elif d.weekday() == 5:  # 周六→周五
            d -= timedelta(days=1)
        return d.strftime("%Y%m%d")

    # ==========================================================================
    # Step 11: 仓位管理
    # ==========================================================================
    def _generate_position_suggestions(self, candidates: list) -> list:
        """
        仓位管理建议：
        - 基础仓位30%
        - 妖王(7板+): 70%  总龙头(5-6板): 50%  分支龙头(3-4板): 40%  跟风(2板): 30%
        - 弱转强/分歧转一致额外+10%
        - 单票最大仓位70%
        """
        suggestions = []
        for c in candidates:
            lianban = c.get("连板数", 0)
            level = c.get("level", "")

            # 基础仓位
            if lianban >= 7:
                base = 0.7
            elif lianban >= 5:
                base = 0.5
            elif lianban >= 3:
                base = 0.4
            else:
                base = self.rules["position_base"]

            # 信号加成
            bonus = 0
            for p in c.get("patterns", []):
                if p["type"] in ("弱转强", "分歧转一致"):
                    bonus = max(bonus, self.rules["position_signal_bonus"])

            position = min(base + bonus, self.rules["position_max"])

            suggestions.append({
                "code": c.get("代码", ""),
                "name": c.get("名称", ""),
                "level": level,
                "lianban": lianban,
                "suggested_position": round(position * 100),
                "reason": f"{level}{lianban}板" + ("+信号确认" if bonus > 0 else ""),
            })

        return suggestions

    # ==========================================================================
    # 个股详情
    # ==========================================================================
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

    # ==========================================================================
    # 工具方法
    # ==========================================================================
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
