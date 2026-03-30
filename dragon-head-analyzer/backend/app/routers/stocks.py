"""
API路由
"""
from fastapi import APIRouter, Query
from datetime import datetime
from ..services.data_fetcher import DataFetcher
from ..services.analyzer import DragonHeadAnalyzer
from ..services.logger import AnalyzerLogger

router = APIRouter(prefix="/api", tags=["龙头战法"])

# 全局实例
fetcher = DataFetcher()
logger = AnalyzerLogger()
analyzer = DragonHeadAnalyzer(fetcher, logger)


@router.get("/scan")
async def scan():
    """全量扫描：涨停池 + 龙头识别 + 信号"""
    result = analyzer.scan_all()
    return {"success": True, "data": result}


@router.get("/zt-pool")
async def zt_pool(date: str = Query(None, description="日期 YYYYMMDD")):
    """涨停股池"""
    df = fetcher.get_zt_pool(date)
    if df.empty:
        return {"success": True, "data": []}
    return {"success": True, "data": df.to_dict(orient="records")}


@router.get("/lb-pool")
async def lb_pool(date: str = Query(None, description="日期 YYYYMMDD")):
    """连板股池"""
    df = fetcher.get_lb_pool(date)
    if df.empty:
        return {"success": True, "data": []}
    return {"success": True, "data": df.to_dict(orient="records")}


@router.get("/zr-pool")
async def zr_pool(date: str = Query(None, description="日期 YYYYMMDD")):
    """炸板股池"""
    df = fetcher.get_zr_pool(date)
    if df.empty:
        return {"success": True, "data": []}
    return {"success": True, "data": df.to_dict(orient="records")}


@router.get("/realtime")
async def realtime():
    """全市场实时行情快照"""
    df = fetcher.get_realtime_quotes()
    if df.empty:
        return {"success": True, "data": []}
    return {"success": True, "data": df.to_dict(orient="records")[:200]}


@router.get("/stock/{code}")
async def stock_detail(code: str):
    """个股详情：分时K线 + 日线 + 资金流"""
    detail = analyzer.get_stock_detail(code)
    return {"success": True, "data": detail}


@router.get("/boards")
async def boards(board_type: str = Query("概念板块", description="板块类型")):
    """板块列表及涨幅排名"""
    df = fetcher.get_board_list(board_type)
    if df.empty:
        return {"success": True, "data": []}
    return {"success": True, "data": df.head(50).to_dict(orient="records")}


@router.get("/logs")
async def logs(date: str = Query(None, description="日期 YYYY-MM-DD")):
    """获取日志"""
    if date:
        content = logger.get_logs(date)
    else:
        content = logger.get_today_logs()
    dates = logger.list_log_dates()
    return {"success": True, "data": {"dates": dates, "content": content}}


@router.post("/scan/trigger")
async def trigger_scan():
    """手动触发扫描"""
    result = analyzer.scan_all()
    # 记录信号到日志
    for s in result.get("signals", []):
        logger.log_signal(s)
    return {"success": True, "data": result}
