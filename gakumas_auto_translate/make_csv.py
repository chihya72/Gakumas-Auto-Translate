"""
CSV生成模块，用于生成CSV文件
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import re
import csv
import json
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist
from gakumas_auto_translate.modules.utils import read_file_with_encoding
from gakumas_auto_translate.modules.preprocessor import preprocess_txt_files

# 获取日志记录器
logger = get_logger("make_csv")

def make_csv():
    """主函数，处理CSV生成流程"""
    # 获取路径
    config_file = get_path("config_file")
    
    # 检查配置文件是否存在
    if not os.path.exists(config_file):
        logger.error(f"配置文件不存在: {config_file}")
        return False
    
    # 读取配置文件
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except json.JSONDecodeError:
        logger.error(f"配置文件格式错误: {config_file}")
        return False
    except Exception as e:
        logger.error(f"读取配置文件时出错: {e}")
        return False
    
    # 获取dump_txt_path
    if 'dump_txt_path' not in config:
        logger.error("配置文件中缺少dump_txt_path设置")
        return False
    
    dump_txt_path = config['dump_txt_path']
    if not os.path.exists(dump_txt_path):
        logger.error(f"dump_txt目录不存在: {dump_txt_path}")
        return False
    
    # 确保目录存在
    ensure_paths_exist(["todo_untranslated_txt", "todo_untranslated_csv_orig"])
    
    # 复制文件到todo目录
    source_dir = dump_txt_path
    dest_dir = get_path("todo_untranslated_txt")
    
    try:
        # 获取源目录文件列表
        txt_files = [f for f in os.listdir(source_dir) if f.endswith(".txt")]
        if not txt_files:
            logger.warning(f"源目录中没有txt文件: {source_dir}")
            return False
        
        # 复制文件
        import shutil
        copied_count = 0
        for filename in txt_files:
            try:
                src = os.path.join(source_dir, filename)
                dst = os.path.join(dest_dir, filename)
                shutil.copy2(src, dst)
                copied_count += 1
            except Exception as e:
                logger.error(f"复制文件失败 {filename}: {e}")
        
        logger.info(f"已复制 {copied_count} 个文件到 {dest_dir}")
        
        # 调用预处理函数
        result = preprocess_txt_files()
        
        if result:
            logger.info("CSV生成完成")
            return True
        else:
            logger.warning("CSV生成过程中出现问题")
            return False
            
    except Exception as e:
        logger.error(f"处理过程中出错: {e}")
        return False

if __name__ == "__main__":
    make_csv()
