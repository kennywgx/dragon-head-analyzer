"""
API路由
"""
import logging
from fastapi import APIRouter, Query, HTTPException
from datetime import datetime
from ..services.data_fetcher import DataFetcher
from ..services.analyzer import DragonHeadAnalyzer
from ..services.logger import AnalyzerLogger
from ..core.scheduler import task_manager, reload_task_schedule

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


# =============================================================================
# 任务管理 API
# =============================================================================

@router.get("/tasks")
async def list_tasks():
    """列出所有任务"""
    try:
        tasks = task_manager.list_tasks()
        scheduled = [t for t in tasks if t["category"] == "scheduled"]
        monitors = [t for t in tasks if t["category"] == "rule_monitor"]
        return {"success": True, "data": {"scheduled": scheduled, "monitors": monitors}}
    except Exception as e:
        logger.exception("获取任务列表失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task(task_id: str):
    """获取单个任务详情"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return {"success": True, "data": task.model_dump()}


@router.post("/tasks/{task_id}/execute")
async def execute_task(task_id: str):
    """手动执行任务"""
    try:
        result = task_manager.execute_task(task_id)
        return {"success": True, "data": result.model_dump()}
    except Exception as e:
        logger.exception(f"执行任务失败: {task_id}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}/enable")
async def enable_task(task_id: str, enabled: bool = Query(True)):
    """启用/禁用任务"""
    ok = task_manager.enable_task(task_id, enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    # 重新注册调度
    reload_task_schedule(task_id)
    return {"success": True, "message": f"任务已{'启用' if enabled else '禁用'}"}


@router.put("/tasks/{task_id}/params")
async def update_task_params(task_id: str, params: dict):
    """更新任务规则参数"""
    ok = task_manager.update_task_params(task_id, params)
    if not ok:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    return {"success": True, "message": "参数已更新"}


@router.get("/tasks/results/recent")
async def task_results_recent(limit: int = Query(50, le=200),
                               task_id: str = Query(None)):
    """获取最近的任务执行结果"""
    try:
        results = task_manager.get_recent_results(limit=limit, task_id=task_id)
        return {"success": True, "data": results}
    except Exception as e:
        logger.exception("获取任务结果失败")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/results/dates")
async def task_result_dates():
    """列出有结果记录的日期"""
    try:
        dates = task_manager.get_result_dates()
        return {"success": True, "data": dates}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/results/{date}")
async def task_results_by_date(date: str):
    """获取指定日期的任务执行结果"""
    try:
        results = task_manager.get_results_by_date(date)
        return {"success": True, "data": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
