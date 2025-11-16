"""
日志配置模块

提供应用程序日志记录功能，包括文件日志和控制台输出。
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def setup_logger(
    name: str = "windsurf_registration",
    level: int = logging.INFO,
    log_dir: Optional[Path] = None,
) -> logging.Logger:
    """
    配置并返回logger实例
    
    Args:
        name: Logger名称
        level: 日志级别
        log_dir: 日志文件目录，None则使用默认路径
        
    Returns:
        配置好的Logger实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 避免重复添加handler
    if logger.handlers:
        return logger
    
    # 创建日志目录
    if log_dir is None:
        log_dir = Path.home() / ".windsurf_registration" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 日志格式
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # 文件处理器（每天一个日志文件）
    log_file = log_dir / f"app_{datetime.now().strftime('%Y%m%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


# 创建默认logger实例
default_logger = setup_logger()
