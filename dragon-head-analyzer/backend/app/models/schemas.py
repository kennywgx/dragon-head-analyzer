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


class TradeSignal(BaseModel):
    time: str
    code: str
    name: str
    type: str
    detail: str
    lianban: Optional[int] = None
    level: Optional[str] = None
    score: Optional[float] = None


class ScanResult(BaseModel):
    date: str
    zt_pool_count: int
    lb_pool_count: int
    zr_pool_count: int
    candidates: list[StockCandidate]
    signals: list[TradeSignal]


class ApiResponse(BaseModel):
    success: bool = True
    message: str = "ok"
    data: Optional[dict | list] = None
