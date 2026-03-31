"""
龙头战法分析系统 - 配置
"""
import os
from pathlib import Path

# 路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 龙头识别规则参数
RULES = {
    # ===== 候选筛选 =====
    "min_lianban_count": 2,          # 至少N板才算龙头候选

    # ===== 板块共振 =====
    "min_board_follow_count": 3,     # 同板块跟涨至少N只才视为板块共振
    "board_resonance_bonus": 10,     # 板块共振加分

    # ===== 封板评分 =====
    "seal_order_ratio_threshold": 0.01,  # 封单额/流通市值比：强封
    "seal_ratio_medium": 0.005,          # 封单额/流通市值比：中等封
    "seal_ratio_weak": 0.002,            # 封单额/流通市值比：弱封
    "morning_limit_up_minutes": 35,      # 早盘封板窗口（分钟，9:25-10:00）

    # ===== 缩量板 =====
    "shrink_volume_ratio": 0.8,     # 当日量/前日量 < 该值视为缩量

    # ===== 弱转强 / 分歧转一致 =====
    "weak_turn_strong_pct": 3.0,     # 前日涨幅<此值（弱板），今日涨停→弱转强
    "consensus_turn_pct": 5.0,       # 前日振幅>此值（分歧板），今日涨停→分歧转一致
    "weak_turn_strong_bonus": 15,    # 弱转强信号加分
    "consensus_turn_bonus": 12,      # 分歧转一致信号加分

    # ===== 卡位介入 =====
    "compete_slot_same_level": 2,    # 同级别（同连板数）存在>=N只竞争时触发卡位判断
    "compete_slot_volume_ratio": 1.5, # 卡位股当日量比需>此值（放量确认）
    "compete_slot_pct_advantage": 3.0, # 涨幅需领先对手>=此百分点

    # ===== 离场信号 =====
    "exit_drop_threshold": -0.05,     # 跌幅阈值
    "exit_high_volume_ratio": 2.0,    # 高位放量：量比放大倍数
    "exit_broken_board": True,        # 断板离场
    "exit_long_yin_pct": -7.0,        # 放量长阴：跌幅阈值
    "exit_long_yin_vol_ratio": 1.8,   # 放量长阴：量比阈值
    "exit_board_retreat_count": 3,    # 板块退潮：同板块跌停>=N只

    # ===== 仓位管理 =====
    "position_base": 0.3,             # 基础仓位30%
    "position_per_level": 0.1,        # 每级加仓10%（妖王最高仓位）
    "position_max": 0.7,              # 单票最大仓位70%
    "position_signal_bonus": 0.1,     # 弱转强/分歧转一致额外+10%

    # ===== K线形态 =====
    "yi_zi_board_open_ratio": 0.001,  # 一字板：开盘价/收盘价差<0.1%
    "t_board_lower_shadow_pct": 0.02, # T字板：下影线/收盘价>2%
}

# 调度配置
SCHEDULER_CONFIG = {
    "market_monitor_interval": 60,
    "close_analysis_hour": 15,
    "close_analysis_minute": 10,
}
