"""
日志服务 - 写入 logs/{date}.log
"""
import os
from datetime import datetime
from pathlib import Path
from ..core.config import LOG_DIR


class AnalyzerLogger:
    """分析日志器"""

    def __init__(self):
        self.log_dir = LOG_DIR
        self.log_dir.mkdir(exist_ok=True)

    def _get_log_file(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.log"

    def log(self, message: str):
        """写入日志"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] {message}\n"
        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line)
        print(line.strip())

    def log_signal(self, signal: dict):
        """记录交易信号"""
        msg = (
            f"SIGNAL | {signal.get('type', '')} | "
            f"{signal.get('code', '')} {signal.get('name', '')} | "
            f"{signal.get('detail', '')}"
        )
        self.log(msg)

    def get_today_logs(self) -> str:
        """读取今日日志"""
        log_file = self._get_log_file()
        if log_file.exists():
            return log_file.read_text(encoding="utf-8")
        return ""

    def get_logs(self, date_str: str) -> str:
        """读取指定日期日志"""
        log_file = self.log_dir / f"{date_str}.log"
        if log_file.exists():
            return log_file.read_text(encoding="utf-8")
        return ""

    def list_log_dates(self) -> list:
        """列出所有日志日期"""
        files = sorted(self.log_dir.glob("*.log"), reverse=True)
        return [f.stem for f in files]
