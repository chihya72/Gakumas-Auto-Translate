"""
日志模块，提供统一的日志记录功能
"""

import os
import logging
from datetime import datetime

# 日志级别映射
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

# 默认日志格式
DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

class Logger:
    """日志记录器类"""
    
    def __init__(self, name, log_dir="logs", level="INFO", console=True):
        """
        初始化日志记录器
        
        参数:
            name: 日志记录器名称
            log_dir: 日志文件目录
            level: 日志级别
            console: 是否输出到控制台
        """
        self.name = name
        self.logger = logging.getLogger(name)
        
        # 设置日志级别
        log_level = LOG_LEVELS.get(level.upper(), logging.INFO)
        self.logger.setLevel(log_level)
        
        # 确保日志目录存在
        if not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 创建日志文件名
        log_file = os.path.join(log_dir, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_formatter = logging.Formatter(DEFAULT_FORMAT)
        file_handler.setFormatter(file_formatter)
        self.logger.addHandler(file_handler)
        
        # 如果需要，创建控制台处理器
        if console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(log_level)
            console_formatter = logging.Formatter(DEFAULT_FORMAT)
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)
    
    def debug(self, message):
        """记录调试信息"""
        self.logger.debug(message)
    
    def info(self, message):
        """记录一般信息"""
        self.logger.info(message)
        # 同时打印到控制台，保持与原有print行为一致
        print(message)
    
    def warning(self, message):
        """记录警告信息"""
        self.logger.warning(message)
        # 同时打印到控制台，保持与原有print行为一致
        print(f"警告: {message}")
    
    def error(self, message):
        """记录错误信息"""
        self.logger.error(message)
        # 同时打印到控制台，保持与原有print行为一致
        print(f"错误: {message}")
    
    def critical(self, message):
        """记录严重错误信息"""
        self.logger.critical(message)
        # 同时打印到控制台，保持与原有print行为一致
        print(f"严重错误: {message}")

# 创建默认日志记录器
default_logger = Logger("gakumas", level="INFO")

def get_logger(name=None):
    """获取日志记录器"""
    if name is None:
        return default_logger
    return Logger(name)
