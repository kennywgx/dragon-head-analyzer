"""
定时调度器
"""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ..services.data_fetcher import DataFetcher
from ..services.analyzer import DragonHeadAnalyzer
from ..services.logger import AnalyzerLogger
from ..core.config import SCHEDULER_CONFIG

scheduler = BackgroundScheduler()
fetcher = DataFetcher()
logger = AnalyzerLogger()
analyzer = DragonHeadAnalyzer(fetcher, logger)


def scheduled_scan():
    """定时扫描任务"""
    logger.log("[定时任务] 开始盘后扫描")
    try:
        result = analyzer.scan_all()
        for s in result.get("signals", []):
            logger.log_signal(s)
        logger.log(f"[定时任务] 扫描完成，{len(result.get('signals', []))} 条信号")
    except Exception as e:
        logger.log(f"[定时任务] 扫描异常: {e}")


def setup_scheduler():
    """注册定时任务"""
    # 每个交易日 15:10 收盘分析
    scheduler.add_job(
        scheduled_scan,
        CronTrigger(
            hour=SCHEDULER_CONFIG["close_analysis_hour"],
            minute=SCHEDULER_CONFIG["close_analysis_minute"],
            day_of_week="mon-fri"
        ),
        id="close_analysis",
        name="收盘龙头扫描"
    )
    scheduler.start()
    logger.log("[调度器] 已启动，收盘分析时间: 周一至周五 15:10")
