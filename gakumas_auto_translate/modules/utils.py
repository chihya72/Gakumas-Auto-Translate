"""
工具模块，包含共享的实用函数
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import re
import json
import pandas as pd
from logger import get_logger
from paths import get_path, normalize_path

# 获取日志记录器
logger = get_logger("utils")

def create_sample_dictionary(dict_file):
    """创建一个示例字典文件"""
    sample_dict = {
        "ことね": "琴音",
        "リーリヤ": "莉莉娅",
        "広": "广"
    }
    
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(dict_file), exist_ok=True)
        
        # 写入示例字典
        with open(dict_file, 'w', encoding='utf-8') as f:
            json.dump(sample_dict, f, ensure_ascii=False, indent=4)
        logger.info(f"已创建示例字典文件: {dict_file}")
        return True
    except Exception as e:
        logger.error(f"创建示例字典文件失败: {e}")
        return False

def clean_html_tags(text):
    """清理文本中的HTML样式标签，只保留标签内的内容"""
    if text is None:
        return text
    
    try:
        # 匹配 <r\=...>内容</r> 只取内容
        text = re.sub(r'<r\\=[^>]+>(.*?)</r>', r'\1', text)
        # 再处理 <em\=...>内容</em>
        text = re.sub(r'<em\\=[^>]*>(.*?)</em>', r'\1', text)
        # 处理 <em>内容</em>
        text = re.sub(r'<em>(.*?)</em>', r'\1', text)
        return text
    except Exception as e:
        logger.error(f"清理HTML标签失败: {e}")
        return text  # 返回原始文本，避免处理失败导致内容丢失

def remove_r_tags_inplace(csv_path):
    """移除文本中的r标签并保存回原文件"""
    try:
        # 使用pandas读取CSV文件
        df = pd.read_csv(csv_path, dtype=str)
        
        # 定义清理文本的函数
        def clean_text(text):
            if pd.isnull(text):
                return text
            return clean_html_tags(text)
        
        # 应用清理函数到'text'列
        df['text'] = df['text'].apply(clean_text)
        
        # 保存回原文件
        df.to_csv(csv_path, index=False, encoding='utf-8')
        logger.info(f"已移除文件中的r标签: {csv_path}")
        return True
    except pd.errors.EmptyDataError:
        logger.warning(f"CSV文件为空: {csv_path}")
        return False
    except Exception as e:
        logger.error(f"移除r标签失败: {e}")
        return False

def ensure_dir_exists(dir_path):
    """确保目录存在，如不存在则创建"""
    try:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            logger.info(f"已创建目录: {dir_path}")
            return True
        return False
    except Exception as e:
        logger.error(f"创建目录失败 {dir_path}: {e}")
        return False

def process_unit_text(text):
    """处理文本中特定标签，用于adv_unit_开头的文件
    
    如果文本以[narration text=或[message text=开头，
    则去除含有'―'属性的r标签，但保留标签内容
    """
    try:
        if text.startswith('[narration text=') or text.startswith('[message text='):
            pattern = r'<r\\=([^>]*)>(.*?)</r>'
            
            def repl(match):
                tag_attrs = match.group(1)  # 标签属性部分
                tag_content = match.group(2)  # 标签内文本

                if '―' in tag_attrs:
                    # 标签属性中包含'―'，去除标签，保留文本
                    return tag_content
                else:
                    return match.group(0)

            new_text = re.sub(pattern, repl, text)
            return new_text
        return text
    except Exception as e:
        logger.error(f"处理文本标签失败: {e}")
        return text  # 返回原始文本，避免处理失败导致内容丢失

def process_unit_file(file_path):
    """处理单个adv_unit_开头的文件"""
    try:
        # 尝试不同的编码
        encodings = ['utf-8', 'shift-jis', 'gbk', 'cp932']
        lines = None
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    lines = f.readlines()
                logger.debug(f"使用 {encoding} 编码成功读取文件: {file_path}")
                break
            except UnicodeDecodeError:
                continue
        
        if lines is None:
            logger.error(f"无法识别文件编码: {file_path}")
            return False
        
        # 处理文本
        new_lines = [process_unit_text(line) for line in lines]
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        logger.info(f'已处理文件: {file_path}')
        return True
    except FileNotFoundError:
        logger.error(f'文件不存在: {file_path}')
        return False
    except PermissionError:
        logger.error(f'无权限访问文件: {file_path}')
        return False
    except Exception as e:
        logger.error(f'处理文件失败 {file_path}: {str(e)}')
        return False

def process_unit_files_in_folder(folder_path):
    """处理文件夹中所有adv_unit_开头的txt文件"""
    try:
        if not os.path.exists(folder_path):
            logger.error(f"目录不存在: {folder_path}")
            return 0
        
        processed_count = 0
        for file in os.listdir(folder_path):
            if file.startswith('adv_unit_') and file.endswith('.txt'):
                file_path = os.path.join(folder_path, file)
                if os.path.isfile(file_path):
                    if process_unit_file(file_path):
                        processed_count += 1
        
        if processed_count > 0:
            logger.info(f"已处理 {processed_count} 个 adv_unit_ 文件")
        else:
            logger.info("未找到需要处理的 adv_unit_ 文件")
        
        return processed_count
    except Exception as e:
        logger.error(f"处理文件夹失败 {folder_path}: {str(e)}")
        return 0

def safe_file_operation(operation_func, *args, **kwargs):
    """安全执行文件操作，处理可能的异常"""
    try:
        return operation_func(*args, **kwargs)
    except FileNotFoundError:
        logger.error(f"文件不存在: {args[0] if args else ''}")
    except PermissionError:
        logger.error(f"无权限访问文件: {args[0] if args else ''}")
    except Exception as e:
        logger.error(f"文件操作失败: {str(e)}")
    return False

def read_file_with_encoding(file_path, encodings=None):
    """尝试使用多种编码读取文件"""
    if encodings is None:
        encodings = ['utf-8', 'shift-jis', 'gbk', 'cp932', 'latin1']
    
    content = None
    used_encoding = None
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            used_encoding = encoding
            break
        except UnicodeDecodeError:
            continue
    
    if content is None:
        logger.error(f"无法识别文件编码: {file_path}")
        return None, None
    
    logger.debug(f"使用 {used_encoding} 编码成功读取文件: {file_path}")
    return content, used_encoding

def validate_input(input_str, input_type='string', min_val=None, max_val=None):
    """验证用户输入"""
    if input_type == 'number':
        try:
            value = int(input_str)
            if min_val is not None and value < min_val:
                return False, f"输入值不能小于 {min_val}"
            if max_val is not None and value > max_val:
                return False, f"输入值不能大于 {max_val}"
            return True, value
        except ValueError:
            return False, "请输入有效的数字"
    elif input_type == 'path':
        # 验证路径格式
        if not os.path.isabs(input_str) and not input_str.startswith('./') and not input_str.startswith('../'):
            return False, "请输入有效的路径"
        return True, input_str
    # 其他类型验证...
    return True, input_str
