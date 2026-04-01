"""
定时调度器 - 集成任务管理系统
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ..services.data_fetcher import DataFetcher
from ..services.analyzer import DragonHeadAnalyzer
from ..services.logger import AnalyzerLogger
from ..services.task_manager import TaskManager
from ..core.config import SCHEDULER_CONFIG

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()
fetcher = DataFetcher()
logger_svc = AnalyzerLogger()
analyzer = DragonHeadAnalyzer(fetcher, logger_svc)
task_manager = TaskManager(fetcher, analyzer, logger_svc)


def _run_task(task_id: str):
    """调度回调：执行任务"""
    try:
        result = task_manager.execute_task(task_id)
        logger.info(f"[Scheduler] {result.name}: {result.summary}")
        # 有告警则记录到日志
        for alert in result.alerts:
            logger_svc.log(f"⚠️ [{alert['type']}] {alert['name']} - {alert['detail']}")
    except Exception as e:
        logger.exception(f"[Scheduler] 任务执行异常: {task_id}")


def setup_scheduler():
    """注册所有启用任务的定时调度"""
    count = 0
    for task in task_manager.tasks.values():
        if not task.enabled:
            continue
        if not task.schedule_type or not task.schedule_expr:
            continue

        try:
            if task.schedule_type == "cron":
                parts = task.schedule_expr.split()
                trigger = CronTrigger(
                    minute=parts[0] if len(parts) > 0 else "*",
                    hour=parts[1] if len(parts) > 1 else "*",
                    day=parts[2] if len(parts) > 2 else "*",
                    month=parts[3] if len(parts) > 3 else "*",
                    day_of_week=parts[4] if len(parts) > 4 else "*",
                )
            elif task.schedule_type == "interval":
                from apscheduler.triggers.interval import IntervalTrigger
                trigger = IntervalTrigger(seconds=int(task.schedule_expr))
            else:
                logger.warning(f"[Scheduler] 不支持的调度类型: {task.schedule_type}")
                continue

            scheduler.add_job(
                _run_task,
                trigger=trigger,
                args=[task.task_id],
                id=task.task_id,
                name=task.name,
                replace_existing=True,
            )
            count += 1
            logger.info(f"[Scheduler] 注册任务: {task.name} ({task.schedule_expr})")
        except Exception as e:
            logger.error(f"[Scheduler] 注册任务失败 {task.task_id}: {e}")

    scheduler.start()
    logger.info(f"[Scheduler] 调度器启动完成，共注册 {count} 个任务")


def reload_task_schedule(task_id: str):
    """重新注册单个任务的调度（启用/禁用后调用）"""
    task = task_manager.get_task(task_id)
    if not task:
        return False

    # 移除旧任务
    try:
        scheduler.remove_job(task_id)
    except Exception:
        pass

    if not task.enabled:
        logger.info(f"[Scheduler] 任务已禁用: {task.name}")
        return True

    if not task.schedule_type or not task.schedule_expr:
        return False

    try:
        parts = task.schedule_expr.split()
        if task.schedule_type == "cron":
            trigger = CronTrigger(
                minute=parts[0] if len(parts) > 0 else "*",
                hour=parts[1] if len(parts) > 1 else "*",
                day=parts[2] if len(parts) > 2 else "*",
                month=parts[3] if len(parts) > 3 else "*",
                day_of_week=parts[4] if len(parts) > 4 else "*",
            )
        elif task.schedule_type == "interval":
            from apscheduler.triggers.interval import IntervalTrigger
            trigger = IntervalTrigger(seconds=int(task.schedule_expr))
        else:
            return False

        scheduler.add_job(
            _run_task,
            trigger=trigger,
            args=[task_id],
            id=task_id,
            name=task.name,
            replace_existing=True,
        )
        logger.info(f"[Scheduler] 重新注册任务: {task.name}")
        return True
    except Exception as e:
        logger.error(f"[Scheduler] 重新注册失败 {task_id}: {e}")
        return False
