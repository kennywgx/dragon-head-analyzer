"""
API路由
"""
import logging
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from ..services.data_fetcher import DataFetcher
from ..services.analyzer import DragonHeadAnalyzer
from ..services.logger import AnalyzerLogger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["龙头战法"])

# 全局实例
fetcher = DataFetcher()
logger_svc = AnalyzerLogger()
analyzer = DragonHeadAnalyzer(fetcher, logger_svc)


@router.get("/scan")
async def scan():
    """全量扫描：涨停池 + 龙头识别 + 信号"""
    try:
        result = analyzer.scan_all()
        return {"success": True, "data": result}
    except Exception as e:
        logger.exception("扫描失败")
        raise HTTPException(status_code=500, detail=f"扫描失败: {str(e)}")


@router.get("/zt-pool")
async def zt_pool(date: str = Query(None, description="日期 YYYYMMDD")):
    """涨停股池"""
    try:
        df = fetcher.get_zt_pool(date)
        if df.empty:
            return {"success": True, "data": []}
        return {"success": True, "data": df.to_dict(orient="records")}
    except Exception as e:
        logger.exception("获取涨停池失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lb-pool")
async def lb_pool(date: str = Query(None, description="日期 YYYYMMDD")):
    """连板股池"""
    try:
        df = fetcher.get_lb_pool(date)
        if df.empty:
            return {"success": True, "data": []}
        return {"success": True, "data": df.to_dict(orient="records")}
    except Exception as e:
        logger.exception("获取连板池失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/zr-pool")
async def zr_pool(date: str = Query(None, description="日期 YYYYMMDD")):
    """炸板股池"""
    try:
        df = fetcher.get_zr_pool(date)
        if df.empty:
            return {"success": True, "data": []}
        return {"success": True, "data": df.to_dict(orient="records")}
    except Exception as e:
        logger.exception("获取炸板池失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime")
async def realtime():
    """全市场实时行情快照"""
    try:
        df = fetcher.get_realtime_quotes()
        if df.empty:
            return {"success": True, "data": []}
        return {"success": True, "data": df.to_dict(orient="records")[:200]}
    except Exception as e:
        logger.exception("获取实时行情失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock/{code}")
async def stock_detail(code: str):
    """个股详情：分时K线 + 日线 + 资金流"""
    try:
        detail = analyzer.get_stock_detail(code)
        return {"success": True, "data": detail}
    except Exception as e:
        logger.exception(f"获取个股详情失败: {code}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/boards")
async def boards(board_type: str = Query("概念板块", description="板块类型")):
    """板块列表及涨幅排名"""
    try:
        df = fetcher.get_board_list(board_type)
        if df.empty:
            return {"success": True, "data": []}
        return {"success": True, "data": df.head(50).to_dict(orient="records")}
    except Exception as e:
        logger.exception("获取板块数据失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs")
async def logs(date: str = Query(None, description="日期 YYYY-MM-DD")):
    """获取日志"""
    try:
        if date:
            content = logger_svc.get_logs(date)
        else:
            content = logger_svc.get_today_logs()
        dates = logger_svc.list_log_dates()
        return {"success": True, "data": {"dates": dates, "content": content}}
    except Exception as e:
        logger.exception("获取日志失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan/trigger")
async def trigger_scan():
    """手动触发扫描"""
    try:
        result = analyzer.scan_all()
        for s in result.get("signals", []):
            logger_svc.log_signal(s)
        return {"success": True, "data": result}
    except Exception as e:
        logger.exception("手动扫描失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_cache(prefix: str = Query(None, description="缓存前缀，为空则清理全部")):
    """手动清理缓存"""
    try:
        fetcher.clear_cache(prefix)
        return {"success": True, "message": "缓存已清理"}
    except Exception as e:
        logger.exception("清理缓存失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/stats")
async def cache_stats():
    """查看缓存统计"""
    try:
        cache_dir = fetcher.cache.cache_dir
        files = list(cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        return {
            "success": True,
            "data": {
                "file_count": len(files),
                "total_size_mb": round(total_size / 1024 / 1024, 2),
                "cache_dir": str(cache_dir),
            }
        }
    except Exception as e:
        logger.exception("获取缓存统计失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok", "version": "0.2.0", "timestamp": datetime.now().isoformat()}
