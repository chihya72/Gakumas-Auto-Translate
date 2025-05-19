"""
工具模块，包含共享的实用函数
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import re
import csv
import json
import shutil
from pathlib import Path
from gakumas_auto_translate.modules.logger import get_logger

# 获取日志记录器
logger = get_logger("utils")

def validate_input(input_str, input_type='text', min_val=None, max_val=None):
    """验证用户输入"""
    if input_type == 'number':
        try:
            value = int(input_str)
            if min_val is not None and value < min_val:
                return False, f"输入值必须大于或等于 {min_val}"
            if max_val is not None and value > max_val:
                return False, f"输入值必须小于或等于 {max_val}"
            return True, value
        except ValueError:
            return False, "请输入有效的数字"
    elif input_type == 'path':
        if not input_str:
            return False, "路径不能为空"
        path = os.path.expanduser(input_str)
        if not os.path.exists(path):
            return False, f"路径不存在: {path}"
        return True, path
    else:  # 默认为文本
        if not input_str:
            return False, "输入不能为空"
        return True, input_str

def read_file_with_encoding(file_path, encodings=None):
    """尝试使用多种编码读取文件，返回内容和使用的编码"""
    if encodings is None:
        encodings = ['utf-8', 'utf-8-sig', 'gbk', 'shift-jis', 'euc-jp']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            return content, encoding
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.error(f"读取文件时出错 {file_path}: {e}")
            return None, None
    
    logger.error(f"无法以任何支持的编码读取文件 {file_path}")
    return None, None

def remove_r_tags(text):
    r"""移除文本中的<r\=></r>标签"""
    if text is None:
        return text
    # 匹配 <r\=...>内容</r> 只取内容
    return re.sub(r'<r\\=[^>]+>(.*?)</r>', r'\1', text)

def remove_r_tags_inplace(file_path):
    r"""直接在文件中移除<r\=></r>标签"""
    try:
        # 读取CSV文件
        rows = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # 处理每一行
        for row in rows:
            if 'text' in row:
                row['text'] = remove_r_tags(row['text'])
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        
        return True
    except Exception as e:
        logger.error(f"处理文件失败 {file_path}: {e}")
        return False

def process_unit_files_in_folder(folder_path):
    """处理文件夹中的adv_unit_开头的文件"""
    try:
        # 获取所有adv_unit_开头的文件
        unit_files = [f for f in os.listdir(folder_path) if f.startswith("adv_unit_") and f.endswith(".txt")]
        
        if not unit_files:
            logger.info("没有找到adv_unit_开头的文件")
            return False
        
        # 按照数字排序
        unit_files.sort(key=lambda x: int(re.search(r'adv_unit_(\d+)', x).group(1)))
        
        # 合并内容
        combined_content = ""
        for file_name in unit_files:
            file_path = os.path.join(folder_path, file_name)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                combined_content += content + "\n"
            except Exception as e:
                logger.error(f"读取文件失败 {file_path}: {e}")
        
        # 写入合并文件
        combined_file = os.path.join(folder_path, "adv_unit_all.txt")
        try:
            with open(combined_file, 'w', encoding='utf-8') as f:
                f.write(combined_content)
            logger.info(f"已合并 {len(unit_files)} 个unit文件到 {combined_file}")
            return True
        except Exception as e:
            logger.error(f"写入合并文件失败 {combined_file}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"处理unit文件时出错: {e}")
        return False
