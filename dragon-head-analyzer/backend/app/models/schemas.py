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
