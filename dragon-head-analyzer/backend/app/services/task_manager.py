"""
任务管理器 - 定时任务 + 规则监听任务

内置任务:
  A. 调度类 (scheduled)
     1. 盘前扫描    周一至周五 09:15  集合竞价异动
     2. 收盘扫描    周一至周五 15:10  全量龙头分析
     3. 周末复盘    周六 10:00        本周数据汇总

  B. 规则监听类 (rule_monitor)
     1. 情绪周期    涨停家数/晋级率/炸板率 → 冰点/高潮判断
     2. 一进二      首板→二板候选筛选 (集合竞价+量能+形态)
     3. 封单强度    实时封单量:成交量比值监控
     4. 板块共振    板块内跟涨股数量检测
     5. 炸板预警    连板股开板实时预警
"""
import json
import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from ..core.config import RULES, BASE_DIR
from ..models.schemas import TaskConfig, TaskResult, EmotionSnapshot

logger = logging.getLogger(__name__)

RESULT_DIR = BASE_DIR / "task_results"
RESULT_DIR.mkdir(exist_ok=True)


# =============================================================================
# 内置任务定义
# =============================================================================
BUILTIN_TASKS: list[dict] = [
    # ──────────── 调度类 ────────────
    {
        "task_id": "pre_market_scan",
        "name": "📋 盘前集合竞价扫描",
        "category": "scheduled",
        "description": "9:15 集合竞价阶段扫描，检测高开异动、封单异常、板块启动信号",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "15 9 * * 1-5",
        "rule_type": None,
        "rule_params": None,
        "notify": True,
    },
    {
        "task_id": "close_scan",
        "name": "📊 收盘全量扫描",
        "category": "scheduled",
        "description": "15:10 收盘后全量扫描：涨停池+龙头识别+信号生成+写日志",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "10 15 * * 1-5",
        "rule_type": None,
        "rule_params": None,
        "notify": True,
    },
    {
        "task_id": "weekend_review",
        "name": "📝 周末复盘汇总",
        "category": "scheduled",
        "description": "周六上午汇总本周扫描数据，统计龙头命中率和信号表现",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "0 10 * * 6",
        "rule_type": None,
        "rule_params": None,
        "notify": True,
    },

    # ──────────── 规则监听类 ────────────
    {
        "task_id": "emotion_monitor",
        "name": "🌡️ 情绪周期监控",
        "category": "rule_monitor",
        "description": "监控涨停家数、连板晋级率、炸板率，判断市场情绪阶段（冰点/退潮/修复/发酵/高潮）",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "*/30 9-15 * * 1-5",
        "rule_type": "emotion",
        "rule_params": {
            "zt_ice_threshold": 20,       # 涨停<20家 → 冰点
            "zt_boom_threshold": 80,      # 涨停>80家 → 高潮
            "break_rate_warn": 0.4,       # 炸板率>40% → 警告
            "promote_rate_strong": 0.3,   # 晋级率>30% → 强势
            "promote_rate_weak": 0.1,     # 晋级率<10% → 弱势
        },
        "notify": True,
    },
    {
        "task_id": "yijiner_scanner",
        "name": "🎯 一进二候选筛选",
        "category": "rule_monitor",
        "description": "筛选昨日首板、今日有望连板的标的：排除烂板/左压未放量，集合竞价高开1%-6%，成交额5-20亿",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "25 9 * * 1-5",   # 9:25 集合竞价结束后
        "rule_type": "yijiner",
        "rule_params": {
            "min_amount": 5.5e8,            # 最低成交额 5.5亿
            "max_amount": 20e8,             # 最高成交额 20亿
            "min_open_pct": 1.0,            # 最低高开幅度
            "max_open_pct": 6.0,            # 最高高开幅度
            "min_market_cap": 50e8,         # 最低流通市值 50亿
            "max_market_cap": 500e8,        # 最高流通市值 500亿
        },
        "notify": True,
    },
    {
        "task_id": "seal_strength_monitor",
        "name": "🔒 封单强度监控",
        "category": "rule_monitor",
        "description": "监控连板股封单量:成交量比值，>5:1强势封板，<2:1弱封预警",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "*/15 9-15 * * 1-5",
        "rule_type": "seal_strength",
        "rule_params": {
            "strong_ratio": 5.0,     # 封单量:成交量 > 5:1 强势
            "medium_ratio": 3.0,     # > 3:1 中等
            "weak_ratio": 2.0,       # < 2:1 弱封预警
        },
        "notify": True,
    },
    {
        "task_id": "sector_resonance_monitor",
        "name": "🔗 板块共振检测",
        "category": "rule_monitor",
        "description": "检测板块内跟涨股≥3只确认共振效应，板块涨幅排名前20%视为强势板块",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "0 10,11,13,14 * * 1-5",  # 10:00,11:00,13:00,14:00
        "rule_type": "sector_resonance",
        "rule_params": {
            "min_follow_count": 3,         # 同板块跟涨至少3只
            "top_pct": 0.2,                # 板块排名前20%
            "min_sector_pct": 2.0,         # 板块涨幅≥2%
        },
        "notify": True,
    },
    {
        "task_id": "breaking_board_alert",
        "name": "🚨 连板股炸板预警",
        "category": "rule_monitor",
        "description": "监控连板股是否开板，连板≥3的标的开板立即预警",
        "enabled": True,
        "schedule_type": "cron",
        "schedule_expr": "*/5 9-15 * * 1-5",
        "rule_type": "breaking_board",
        "rule_params": {
            "min_lianban": 3,        # 只监控3板以上
            "alert_cooldown": 300,   # 同一只股5分钟内不重复报警
        },
        "notify": True,
    },
]


# =============================================================================
# 任务管理器
# =============================================================================
class TaskManager:
    """任务管理器：CRUD + 执行 + 结果存储"""

    def __init__(self, fetcher, analyzer, logger_svc):
        self.fetcher = fetcher
        self.analyzer = analyzer
        self.logger_svc = logger_svc
        self.tasks: dict[str, TaskConfig] = {}
        self.results: list[TaskResult] = []
        self._alert_cooldown: dict[str, float] = {}  # task_id:code → timestamp
        self._load_builtin_tasks()

    def _load_builtin_tasks(self):
        """加载内置任务"""
        for t in BUILTIN_TASKS:
            self.tasks[t["task_id"]] = TaskConfig(**t)
        logger.info(f"加载 {len(self.tasks)} 个内置任务")

    # =========================================================================
    # CRUD
    # =========================================================================
    def list_tasks(self) -> list[dict]:
        """列出所有任务"""
        return [t.model_dump() for t in self.tasks.values()]

    def get_task(self, task_id: str) -> Optional[TaskConfig]:
        return self.tasks.get(task_id)

    def enable_task(self, task_id: str, enabled: bool = True) -> bool:
        """启用/禁用任务"""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = enabled
            return True
        return False

    def update_task_params(self, task_id: str, params: dict) -> bool:
        """更新任务参数"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            if task.rule_params:
                task.rule_params.update(params)
            else:
                task.rule_params = params
            return True
        return False

    # =========================================================================
    # 执行入口
    # =========================================================================
    def execute_task(self, task_id: str) -> TaskResult:
        """执行单个任务"""
        task = self.tasks.get(task_id)
        if not task:
            return TaskResult(
                task_id=task_id, name="未知任务",
                executed_at=datetime.now().isoformat(),
                status="error", category="unknown",
                summary=f"任务 {task_id} 不存在"
            )

        if not task.enabled:
            return TaskResult(
                task_id=task_id, name=task.name,
                executed_at=datetime.now().isoformat(),
                status="skipped", category=task.category,
                summary="任务已禁用"
            )

        now = datetime.now()
        logger.info(f"[Task] 执行任务: {task.name} ({task_id})")

        try:
            if task.category == "scheduled":
                result = self._execute_scheduled(task)
            elif task.category == "rule_monitor":
                result = self._execute_rule(task)
            else:
                result = TaskResult(
                    task_id=task_id, name=task.name,
                    executed_at=now.isoformat(),
                    status="error", category=task.category,
                    summary=f"未知任务类别: {task.category}"
                )
        except Exception as e:
            logger.exception(f"[Task] 任务执行异常: {task_id}")
            result = TaskResult(
                task_id=task_id, name=task.name,
                executed_at=now.isoformat(),
                status="error", category=task.category,
                summary=f"执行异常: {str(e)}"
            )

        # 存储结果
        self.results.append(result)
        self._save_result(result)
        # 只保留最近 200 条
        if len(self.results) > 200:
            self.results = self.results[-200:]

        return result

    # =========================================================================
    # 调度类任务执行
    # =========================================================================
    def _execute_scheduled(self, task: TaskConfig) -> TaskResult:
        now = datetime.now()

        if task.task_id == "pre_market_scan":
            return self._task_pre_market_scan(task, now)
        elif task.task_id == "close_scan":
            return self._task_close_scan(task, now)
        elif task.task_id == "weekend_review":
            return self._task_weekend_review(task, now)
        else:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="error", category="scheduled",
                summary=f"未实现的调度任务: {task.task_id}"
            )

    def _task_pre_market_scan(self, task: TaskConfig, now: datetime) -> TaskResult:
        """盘前扫描：集合竞价异动"""
        alerts = []

        # 获取涨停池看是否有新面孔
        zt = self.fetcher.get_zt_pool()
        zt_count = len(zt) if not zt.empty else 0

        # 获取连板池
        lb = self.fetcher.get_lb_pool()
        lb_count = len(lb) if not lb.empty else 0

        # 高开异动检测：通过实时行情看涨停股集合竞价量
        if not zt.empty and "连板数" in zt.columns:
            first_board = zt[zt["连板数"] == 1]
            for _, row in first_board.iterrows():
                name = str(row.get("名称", ""))
                code = str(row.get("代码", ""))
                pct = float(row.get("涨跌幅", 0) or 0)
                if pct >= 9.9:
                    alerts.append({
                        "type": "首板涨停",
                        "code": code,
                        "name": name,
                        "detail": f"开盘即封涨停，涨幅 {pct:.1f}%",
                        "severity": "medium",
                    })

        summary = f"盘前扫描完成: 涨停{zt_count}只, 连板{lb_count}只, 异动{len(alerts)}条"
        logger.info(f"[Task] {summary}")

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="scheduled",
            summary=summary,
            data={"zt_count": zt_count, "lb_count": lb_count},
            alerts=alerts,
        )

    def _task_close_scan(self, task: TaskConfig, now: datetime) -> TaskResult:
        """收盘全量扫描"""
        scan_result = self.analyzer.scan_all()
        signals = scan_result.get("signals", [])
        exit_signals = scan_result.get("exit_signals", [])
        candidates = scan_result.get("candidates", [])

        # 记录信号到日志
        for s in signals:
            self.logger_svc.log_signal(s)

        summary = (
            f"收盘扫描完成: 涨停{scan_result.get('zt_pool_count', 0)}只, "
            f"连板{scan_result.get('lb_pool_count', 0)}只, "
            f"炸板{scan_result.get('zr_pool_count', 0)}只, "
            f"候选{len(candidates)}只, "
            f"信号{len(signals)}条, 离场{len(exit_signals)}条"
        )

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="scheduled",
            summary=summary,
            data=scan_result,
            alerts=[{"type": s["type"], "code": s["code"], "name": s["name"], "detail": s["detail"]}
                    for s in exit_signals],
        )

    def _task_weekend_review(self, task: TaskConfig, now: datetime) -> TaskResult:
        """周末复盘：汇总本周日志"""
        dates = self.logger_svc.list_log_dates()
        this_week = []
        today = now.date()
        monday = today - timedelta(days=today.weekday())

        for d in dates:
            try:
                log_date = datetime.strptime(d, "%Y-%m-%d").date()
                if monday <= log_date <= today:
                    this_week.append(d)
            except ValueError:
                continue

        total_signals = 0
        for d in this_week:
            content = self.logger_svc.get_logs(d)
            total_signals += content.count("SIGNAL")

        summary = f"本周复盘: {len(this_week)}个交易日, 共产生{total_signals}条信号"

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="scheduled",
            summary=summary,
            data={"trade_days": this_week, "total_signals": total_signals},
        )

    # =========================================================================
    # 规则监听类任务执行
    # =========================================================================
    def _execute_rule(self, task: TaskConfig) -> TaskResult:
        now = datetime.now()
        params = task.rule_params or {}

        if task.rule_type == "emotion":
            return self._rule_emotion(task, now, params)
        elif task.rule_type == "yijiner":
            return self._rule_yijiner(task, now, params)
        elif task.rule_type == "seal_strength":
            return self._rule_seal_strength(task, now, params)
        elif task.rule_type == "sector_resonance":
            return self._rule_sector_resonance(task, now, params)
        elif task.rule_type == "breaking_board":
            return self._rule_breaking_board(task, now, params)
        else:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="error", category="rule_monitor",
                summary=f"未知规则类型: {task.rule_type}"
            )

    # ─── 情绪周期 ───────────────────────────────────────────
    def _rule_emotion(self, task: TaskConfig, now: datetime, params: dict) -> TaskResult:
        """
        情绪周期监控
        指标：涨停家数、炸板家数、连板家数、最高连板、晋级率、炸板率
        阶段：冰点(<20涨停) / 退潮(炸板率>40%) / 修复 / 发酵(晋级率>30%) / 高潮(>80涨停)
        """
        zt = self.fetcher.get_zt_pool()
        zr = self.fetcher.get_zr_pool()
        lb = self.fetcher.get_lb_pool()

        zt_count = len(zt) if not zt.empty else 0
        zr_count = len(zr) if not zr.empty else 0
        lb_count = len(lb) if not lb.empty else 0

        # 最高连板数
        max_lb = 0
        if not zt.empty and "连板数" in zt.columns:
            max_lb = int(zt["连板数"].max() or 0)

        # 炸板率
        total = zt_count + zr_count
        break_rate = zr_count / total if total > 0 else 0

        # 晋级率 (需要昨日数据)
        promote_rate = 0.0
        try:
            yesterday = self._get_prev_trade_date()
            yesterday_zt = self.fetcher.get_zt_pool(yesterday)
            if not yesterday_zt.empty:
                yesterday_count = len(yesterday_zt)
                promote_rate = lb_count / yesterday_count if yesterday_count > 0 else 0
        except Exception:
            pass

        # 情绪阶段判断
        phase, score = self._calc_emotion_phase(
            zt_count, break_rate, promote_rate, max_lb, params
        )

        snapshot = EmotionSnapshot(
            date=now.strftime("%Y%m%d"),
            time=now.strftime("%H:%M"),
            zt_count=zt_count, zr_count=zr_count, lb_count=lb_count,
            max_lianban=max_lb, promote_rate=round(promote_rate, 3),
            break_rate=round(break_rate, 3),
            emotion_phase=phase, score=score,
        )

        alerts = []
        if phase == "冰点":
            alerts.append({
                "type": "情绪冰点",
                "code": "MARKET", "name": "市场整体",
                "detail": f"涨停仅{zt_count}只，市场情绪极度低迷，建议空仓等待",
                "severity": "high",
            })
        elif phase == "高潮":
            alerts.append({
                "type": "情绪高潮",
                "code": "MARKET", "name": "市场整体",
                "detail": f"涨停{zt_count}只，市场情绪过热，注意退潮风险",
                "severity": "high",
            })
        if break_rate > params.get("break_rate_warn", 0.4):
            alerts.append({
                "type": "炸板率偏高",
                "code": "MARKET", "name": "市场整体",
                "detail": f"炸板率{break_rate:.0%}，资金分歧严重",
                "severity": "medium",
            })

        summary = (
            f"情绪[{phase}] 得分{score}: "
            f"涨停{zt_count} 炸板{zr_count} 连板{lb_count} "
            f"最高{max_lb}板 晋级率{promote_rate:.0%} 炸板率{break_rate:.0%}"
        )

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="rule_monitor",
            summary=summary,
            data=snapshot.model_dump(),
            alerts=alerts,
        )

    def _calc_emotion_phase(self, zt_count, break_rate, promote_rate, max_lb, params):
        """计算情绪阶段和得分"""
        score = 50  # 基准分

        # 涨停家数评分 (0-40)
        if zt_count >= params.get("zt_boom_threshold", 80):
            score += 40
        elif zt_count >= 50:
            score += 30
        elif zt_count >= 30:
            score += 15
        elif zt_count >= params.get("zt_ice_threshold", 20):
            score -= 10
        else:
            score -= 30

        # 晋级率评分 (-15 ~ +15)
        if promote_rate >= params.get("promote_rate_strong", 0.3):
            score += 15
        elif promote_rate < params.get("promote_rate_weak", 0.1):
            score -= 15

        # 炸板率评分 (-15 ~ 0)
        if break_rate > params.get("break_rate_warn", 0.4):
            score -= 15
        elif break_rate > 0.25:
            score -= 5

        # 最高连板评分 (0-10)
        if max_lb >= 7:
            score += 10
        elif max_lb >= 5:
            score += 5

        score = max(0, min(100, score))

        # 阶段判断
        if zt_count < params.get("zt_ice_threshold", 20):
            phase = "冰点"
        elif break_rate > params.get("break_rate_warn", 0.4):
            phase = "退潮"
        elif score >= 75:
            phase = "高潮"
        elif score >= 55:
            phase = "发酵"
        else:
            phase = "修复"

        return phase, score

    # ─── 一进二筛选 ────────────────────────────────────────
    def _rule_yijiner(self, task: TaskConfig, now: datetime, params: dict) -> TaskResult:
        """
        一进二候选筛选
        条件：
          1. 昨日首板 (涨停池中连板数=1)
          2. 排除烂板 (封单额/流通市值过低)
          3. 成交额在 5-20 亿区间
          4. 流通市值 50-500 亿
          5. 集合竞价高开 1%-6% (通过实时涨幅判断)
        """
        alerts = []
        candidates = []

        zt = self.fetcher.get_zt_pool()
        if zt.empty:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="success", category="rule_monitor",
                summary="涨停池为空，无一进二候选",
            )

        # 筛选首板
        if "连板数" not in zt.columns:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="success", category="rule_monitor",
                summary="涨停池缺少连板数字段",
            )

        first_board = zt[zt["连板数"] == 1]
        min_amount = params.get("min_amount", 5.5e8)
        max_amount = params.get("max_amount", 20e8)
        min_pct = params.get("min_open_pct", 1.0)
        max_pct = params.get("max_open_pct", 6.0)

        for _, row in first_board.iterrows():
            code = str(row.get("代码", ""))
            name = str(row.get("名称", ""))
            pct = float(row.get("涨跌幅", 0) or 0)
            amount = float(row.get("成交额", 0) or 0)
            circ_mv = float(row.get("流通市值", 0) or 0)
            seal_amount = float(row.get("封单额", 0) or 0)

            # 成交额过滤
            if not (min_amount <= amount <= max_amount):
                continue

            # 流通市值过滤
            min_cap = params.get("min_market_cap", 50e8)
            max_cap = params.get("max_market_cap", 500e8)
            if circ_mv > 0 and not (min_cap <= circ_mv <= max_cap):
                continue

            # 排除烂板：封单额占比太低
            is_bad = False
            if circ_mv > 0 and seal_amount > 0:
                seal_ratio = seal_amount / circ_mv
                if seal_ratio < 0.002:  # 弱封标准
                    is_bad = True

            if is_bad:
                continue

            # 涨幅在合理区间 (视为集合竞价高开)
            if min_pct <= pct <= max_pct + 9.9:  # 涨停也算
                pass  # 通过

            score = 0
            score += 10  # 首板基础分
            if circ_mv > 0 and seal_amount > 0:
                ratio = seal_amount / circ_mv
                if ratio >= 0.01:
                    score += 15
                elif ratio >= 0.005:
                    score += 8
            if pct >= 9.9:
                score += 10

            candidates.append({
                "code": code, "name": name,
                "pct_chg": pct, "amount": amount,
                "seal_amount": seal_amount, "circ_mv": circ_mv,
                "score": score,
            })

            alerts.append({
                "type": "一进二候选",
                "code": code, "name": name,
                "detail": f"首板涨停，成交额{amount/1e8:.1f}亿，评分{score}",
                "severity": "medium",
            })

        # 按评分排序
        candidates.sort(key=lambda x: x["score"], reverse=True)

        summary = f"一进二筛选: {len(first_board)}只首板 → {len(candidates)}只候选"

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="rule_monitor",
            summary=summary,
            data={"candidates": candidates},
            alerts=alerts,
        )

    # ─── 封单强度 ───────────────────────────────────────────
    def _rule_seal_strength(self, task: TaskConfig, now: datetime, params: dict) -> TaskResult:
        """
        封单强度监控
        计算封单量:成交量比值，判断封板力度
        """
        alerts = []
        data = []

        lb = self.fetcher.get_lb_pool()
        if lb.empty:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="success", category="rule_monitor",
                summary="连板池为空",
            )

        strong_ratio = params.get("strong_ratio", 5.0)
        weak_ratio = params.get("weak_ratio", 2.0)

        for _, row in lb.iterrows():
            code = str(row.get("代码", ""))
            name = str(row.get("名称", ""))
            lianban = int(row.get("连板数", 0) or 0)
            seal_amount = float(row.get("封单额", 0) or 0)
            amount = float(row.get("成交额", 0) or 0)

            if amount <= 0:
                continue

            ratio = seal_amount / amount
            strength = "强势" if ratio >= strong_ratio else ("中等" if ratio >= params.get("medium_ratio", 3.0) else "弱封")

            data.append({
                "code": code, "name": name, "lianban": lianban,
                "seal_amount": seal_amount, "amount": amount,
                "ratio": round(ratio, 2), "strength": strength,
            })

            # 弱封预警 (连板≥2才预警)
            if ratio < weak_ratio and lianban >= 2:
                key = f"{task.task_id}:{code}"
                last_alert = self._alert_cooldown.get(key, 0)
                if now.timestamp() - last_alert > 300:  # 5分钟冷却
                    alerts.append({
                        "type": "弱封预警",
                        "code": code, "name": name,
                        "detail": f"{lianban}连板，封单量:成交量={ratio:.1f}:1，封板力度弱",
                        "severity": "high" if lianban >= 5 else "medium",
                    })
                    self._alert_cooldown[key] = now.timestamp()

        summary = f"封单监控: {len(data)}只连板股, {len(alerts)}条预警"

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="rule_monitor",
            summary=summary,
            data={"stocks": data},
            alerts=alerts,
        )

    # ─── 板块共振 ───────────────────────────────────────────
    def _rule_sector_resonance(self, task: TaskConfig, now: datetime, params: dict) -> TaskResult:
        """
        板块共振检测
        如果某板块有多只股票涨停/大涨，视为板块共振
        """
        alerts = []

        zt = self.fetcher.get_zt_pool()
        if zt.empty:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="success", category="rule_monitor",
                summary="涨停池为空",
            )

        # 获取板块排名
        boards = self.fetcher.get_board_list("概念板块")
        if boards.empty:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="success", category="rule_monitor",
                summary="板块数据为空",
            )

        top_pct = params.get("top_pct", 0.2)
        min_sector_pct = params.get("min_sector_pct", 2.0)

        # 按涨幅排序，取前20%
        sorted_boards = boards.sort_values(by="涨跌幅", ascending=False).reset_index(drop=True)
        top_n = max(1, int(len(sorted_boards) * top_pct))
        top_boards = sorted_boards.head(top_n)

        strong_sectors = []
        for _, row in top_boards.iterrows():
            name = str(row.get("板块名称", ""))
            pct = float(row.get("涨跌幅", 0) or 0)
            up_count = int(row.get("上涨家数", 0) or 0)

            if pct >= min_sector_pct:
                strong_sectors.append({
                    "name": name, "pct": pct,
                    "up_count": up_count,
                })
                alerts.append({
                    "type": "板块共振",
                    "code": "SECTOR", "name": name,
                    "detail": f"涨幅+{pct:.1f}%，上涨{up_count}家，板块强势",
                    "severity": "medium",
                })

        summary = f"板块共振: {len(strong_sectors)}个强势板块 (涨幅≥{min_sector_pct}%)"

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="rule_monitor",
            summary=summary,
            data={"strong_sectors": strong_sectors},
            alerts=alerts[:10],  # 最多10条
        )

    # ─── 炸板预警 ───────────────────────────────────────────
    def _rule_breaking_board(self, task: TaskConfig, now: datetime, params: dict) -> TaskResult:
        """
        连板股炸板预警
        检测连板池中股票是否被炸板
        """
        alerts = []
        min_lb = params.get("min_lianban", 3)
        cooldown = params.get("alert_cooldown", 300)

        lb = self.fetcher.get_lb_pool()
        zt = self.fetcher.get_zt_pool()

        if lb.empty:
            return TaskResult(
                task_id=task.task_id, name=task.name,
                executed_at=now.isoformat(),
                status="success", category="rule_monitor",
                summary="连板池为空",
            )

        # 获取今日涨停代码
        zt_codes = set()
        if not zt.empty:
            for _, row in zt.iterrows():
                code = str(row.get("代码", ""))
                if code:
                    zt_codes.add(code)

        # 检查高连板股是否还在涨停池
        for _, row in lb.iterrows():
            code = str(row.get("代码", ""))
            name = str(row.get("名称", ""))
            lianban = int(row.get("连板数", 0) or 0)

            if lianban < min_lb:
                continue

            if code not in zt_codes:
                key = f"{task.task_id}:{code}"
                last_alert = self._alert_cooldown.get(key, 0)
                if now.timestamp() - last_alert > cooldown:
                    alerts.append({
                        "type": "炸板预警",
                        "code": code, "name": name,
                        "detail": f"{lianban}连板股已不在涨停池，可能已炸板",
                        "severity": "high",
                    })
                    self._alert_cooldown[key] = now.timestamp()

        summary = f"炸板监控: 检查{len(lb)}只连板股, {len(alerts)}条预警"

        return TaskResult(
            task_id=task.task_id, name=task.name,
            executed_at=now.isoformat(),
            status="success", category="rule_monitor",
            summary=summary,
            alerts=alerts,
        )

    # =========================================================================
    # 结果存储
    # =========================================================================
    def _save_result(self, result: TaskResult):
        """保存执行结果到文件"""
        date_str = datetime.now().strftime("%Y-%m-%d")
        filepath = RESULT_DIR / f"{date_str}.jsonl"
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(result.model_dump(), ensure_ascii=False, default=str) + "\n")
        except IOError as e:
            logger.error(f"[Task] 保存结果失败: {e}")

    def get_recent_results(self, limit: int = 50, task_id: str = None) -> list[dict]:
        """获取最近的执行结果"""
        results = self.results
        if task_id:
            results = [r for r in results if r.task_id == task_id]
        return [r.model_dump() for r in results[-limit:]]

    def get_result_dates(self) -> list[str]:
        """列出有结果记录的日期"""
        files = sorted(RESULT_DIR.glob("*.jsonl"), reverse=True)
        return [f.stem for f in files]

    def get_results_by_date(self, date_str: str) -> list[dict]:
        """获取指定日期的结果"""
        filepath = RESULT_DIR / f"{date_str}.jsonl"
        if not filepath.exists():
            return []
        results = []
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        results.append(json.loads(line))
        except (json.JSONDecodeError, IOError):
            pass
        return results

    # =========================================================================
    # 工具
    # =========================================================================
    def _get_prev_trade_date(self) -> str:
        """获取上一个交易日"""
        d = datetime.now() - timedelta(days=1)
        if d.weekday() == 6:
            d -= timedelta(days=2)
        elif d.weekday() == 5:
            d -= timedelta(days=1)
        return d.strftime("%Y%m%d")
