"""
日志模块，提供统一的日志记录功能
"""

import os
import logging
from datetime import datetime

# 日志级别映射
LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL
}

# 日志格式
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# 日志实例缓存
_loggers = {}

def get_logger(name, level="info", log_to_file=True):
    """
    获取日志记录器
    
    参数:
        name: 日志记录器名称
        level: 日志级别，可选值：debug, info, warning, error, critical
        log_to_file: 是否记录到文件
    
    返回:
        logger: 日志记录器实例
    """
    # 如果已经创建过，直接返回缓存的实例
    if name in _loggers:
        return _loggers[name]
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    
    # 设置日志级别
    logger.setLevel(LOG_LEVELS.get(level.lower(), logging.INFO))
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(console_handler)
    
    # 如果需要记录到文件
    if log_to_file:
        try:
            # 获取项目根目录
            # 注意：这里不直接导入paths模块，避免循环导入
            module_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(os.path.dirname(module_dir))
            logs_dir = os.path.join(base_dir, "logs")
            
            # 确保日志目录存在
            os.makedirs(logs_dir, exist_ok=True)
            
            # 创建日志文件名，使用当前日期
            log_file = os.path.join(
                logs_dir, 
                f"{datetime.now().strftime('%Y-%m-%d')}.log"
            )
            
            # 创建文件处理器
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(LOG_FORMAT))
            logger.addHandler(file_handler)
        except Exception as e:
            # 如果创建文件处理器失败，记录错误但不中断程序
            logger.error(f"创建日志文件处理器失败: {e}")
    
    # 缓存日志记录器实例
    _loggers[name] = logger
    
    return logger
