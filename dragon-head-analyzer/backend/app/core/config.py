"""
龙头战法分析系统 - 配置
"""
import os
from pathlib import Path

# 路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 龙头识别规则参数（后续可从配置文件加载）
RULES = {
    # 连板高度阈值：至少N板才算龙头候选
    "min_lianban_count": 2,
    # 板块共振：涨停当天带动同板块个股跟涨>=N只
    "min_board_follow_count": 3,
    # 早盘封板时间窗口（分钟）
    "morning_limit_up_minutes": 35,  # 9:25-10:00
    # 封单额/流通市值比阈值
    "seal_order_ratio_threshold": 0.01,
    # 缩量板：量比阈值（当日量/前日量 < 该值视为缩量）
    "shrink_volume_ratio": 0.8,
    # 离场：跌幅阈值
    "exit_drop_threshold": -0.05,
    # 高位放量：量比放大倍数
    "high_volume_ratio": 2.0,
}

# 调度配置
SCHEDULER_CONFIG = {
    # 盘中监控间隔（秒）
    "market_monitor_interval": 60,
    # 收盘分析时间
    "close_analysis_hour": 15,
    "close_analysis_minute": 10,
}
