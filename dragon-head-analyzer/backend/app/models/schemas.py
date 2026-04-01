"""
数据模型
"""
from pydantic import BaseModel
from typing import Optional


class StockCandidate(BaseModel):
    code: str
    name: str
    lianban: int
    level: str
    seal_score: float
    pct_chg: Optional[float] = None
    seal_amount: Optional[float] = None
    circ_mv: Optional[float] = None
    turnover: Optional[float] = None
    board_bonus: Optional[float] = 0
    patterns: Optional[list] = []
    compete_slot: Optional[dict] = None
    kline_patterns: Optional[list] = []


class TradeSignal(BaseModel):
    time: str
    code: str
    name: str
    type: str
    detail: str
    lianban: Optional[int] = None
    level: Optional[str] = None
    score: Optional[float] = None
    severity: Optional[str] = None


class ExitSignal(BaseModel):
    time: str
    code: str
    name: str
    type: str
    detail: str
    severity: str = "medium"


class PositionSuggestion(BaseModel):
    code: str
    name: str
    level: str
    lianban: int
    suggested_position: int
    reason: str


class ScanResult(BaseModel):
    date: str
    zt_pool_count: int
    lb_pool_count: int
    zr_pool_count: int
    candidates: list[StockCandidate]
    signals: list[TradeSignal]
    exit_signals: list[ExitSignal] = []
    position_suggestions: list[PositionSuggestion] = []


class ApiResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Optional[dict | list] = None


# =============================================================================
# 任务系统模型
# =============================================================================

class TaskConfig(BaseModel):
    """任务配置"""
    task_id: str
    name: str
    category: str  # scheduled | rule_monitor
    description: str = ""
    enabled: bool = True
    # 调度类任务
    schedule_type: Optional[str] = None   # cron | interval | once
    schedule_expr: Optional[str] = None   # cron 表达式或 interval 秒数
    # 规则监听类任务
    rule_type: Optional[str] = None       # emotion | yijiner | seal_strength | sector_resonance | breaking_board
    rule_params: Optional[dict] = None    # 规则参数
    # 通知
    notify: bool = True


class TaskResult(BaseModel):
    """任务执行结果"""
    task_id: str
    name: str
    executed_at: str
    status: str           # success | error | skipped
    category: str
    summary: str = ""
    data: Optional[dict] = None
    alerts: list = []     # 触发的告警列表


class EmotionSnapshot(BaseModel):
    """市场情绪快照"""
    date: str
    time: str
    zt_count: int = 0         # 涨停家数
    zr_count: int = 0         # 炸板家数
    lb_count: int = 0         # 连板家数
    max_lianban: int = 0      # 最高连板数
    promote_rate: float = 0.0 # 连板晋级率 (今日连板 / 昨日涨停)
    break_rate: float = 0.0   # 炸板率 (炸板 / (涨停+炸板))
    emotion_phase: str = ""   # 冰点 | 退潮 | 修复 | 发酵 | 高潮
    score: int = 0            # 情绪分 (0-100)
