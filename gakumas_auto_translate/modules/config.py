"""
配置模块，负责处理程序配置和目录设置
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import json
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist

# 获取日志记录器
logger = get_logger("config")

def load_config():
    """加载配置文件"""
    config_file = get_path("config_file")
    
    if not os.path.exists(config_file):
        logger.info(f"配置文件不存在: {config_file}")
        print(f"配置文件不存在: {config_file}")
        return False
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # 检查必要的配置项
        if 'dump_txt_path' not in config:
            logger.warning("配置文件中缺少dump_txt_path设置")
            return False
            
        # 检查dump_txt_path是否存在
        dump_txt_path = config['dump_txt_path']
        if not os.path.exists(dump_txt_path):
            logger.warning(f"dump_txt目录不存在: {dump_txt_path}")
            return False
            
        logger.info(f"成功加载配置，dump_txt_path: {dump_txt_path}")
        return True
        
    except json.JSONDecodeError:
        logger.error(f"配置文件格式错误: {config_file}")
        return False
    except Exception as e:
        logger.error(f"加载配置文件时出错: {e}")
        return False

def get_dump_txt_path():
    """获取dump_txt_path配置"""
    config_file = get_path("config_file")
    
    if not os.path.exists(config_file):
        logger.info(f"配置文件不存在: {config_file}")
        return None
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        # 检查必要的配置项
        if 'dump_txt_path' not in config:
            logger.warning("配置文件中缺少dump_txt_path设置")
            return None
            
        # 返回dump_txt_path
        return config['dump_txt_path']
        
    except Exception as e:
        logger.error(f"获取dump_txt_path时出错: {e}")
        return None

def configure_directories():
    """配置程序所需目录"""
    # 确保基本目录结构存在
    ensure_paths_exist([
        "data_dir", 
        "csv_data_dir", 
        "todo_dir",
        "todo_untranslated_txt",
        "todo_untranslated_csv_orig",
        "todo_untranslated_csv_dict",
        "todo_translated_csv",
        "todo_translated_txt",
        "logs_dir"
    ])
    
    # 获取dump_txt_path
    dump_txt_path = get_dump_txt_path()
    
    # 如果已经配置过，询问是否重新配置
    if dump_txt_path and os.path.exists(dump_txt_path):
        print(f"\n当前dump_txt路径: {dump_txt_path}")
        choice = input("是否重新配置？(y/n): ").strip().lower()
        if choice != 'y':
            return dump_txt_path
    
    # 获取新的dump_txt_path
    print("\n请输入游戏文本目录路径（包含.txt文件的目录）:")
    new_path = input("路径: ").strip()
    
    # 验证路径
    if not new_path:
        logger.error("路径不能为空")
        return None
        
    # 处理路径中的引号
    new_path = new_path.strip('"\'')
    
    # 处理相对路径
    if not os.path.isabs(new_path):
        new_path = os.path.abspath(new_path)
    
    # 检查路径是否存在
    if not os.path.exists(new_path):
        logger.error(f"路径不存在: {new_path}")
        return None
        
    # 检查是否为目录
    if not os.path.isdir(new_path):
        logger.error(f"路径不是目录: {new_path}")
        return None
        
    # 检查目录中是否有txt文件
    txt_files = [f for f in os.listdir(new_path) if f.endswith('.txt')]
    if not txt_files:
        logger.warning(f"目录中没有找到txt文件: {new_path}")
        confirm = input("确定使用此目录？(y/n): ").strip().lower()
        if confirm != 'y':
            return None
    
    # 保存配置
    config = {'dump_txt_path': new_path}
    config_file = get_path("config_file")
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        logger.info(f"配置已保存: {config_file}")
        return new_path
    except Exception as e:
        logger.error(f"保存配置时出错: {e}")
        return None
