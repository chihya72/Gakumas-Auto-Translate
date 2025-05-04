#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import logging
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,  # 将日志级别设置为DEBUG以便看到更多信息
    format='%(asctime)s - %(levelname)s - %(message)s',
    filename='punctuation_fix.log'
)
console = logging.StreamHandler()
console.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger('').addHandler(console)

def count_ellipsis_density(text):
    """计算省略号的密度并返回相应的中文省略号"""
    # 统计原文中的省略号密度
    dots_count = 0
    
    # 匹配所有的省略号形式
    dot_patterns = {
        r'(…+)': lambda m: len(m.group(1)) * 3,  # 每个日文省略号…相当于三个点
        r'(\.{2,})': lambda m: len(m.group(1)),  # 每个.算作1个点
        r'(。{2,})': lambda m: len(m.group(1)) * 3  # 每个。算作3个点
    }
    
    for pattern, counter in dot_patterns.items():
        matches = re.finditer(pattern, text)
        for match in matches:
            dots_count += counter(match)
    
    # 日文中每3个点对应中文中2个点（1个中文省略号"……"有6个点）
    cn_dots_count = (dots_count + 2) // 3  # 向上取整除以3

    # 确保至少有2个中文点（1个标准省略号）
    if cn_dots_count < 2:
        cn_dots_count = 2
    
    # 生成对应数量的中文省略号，每个省略号是2个点
    chinese_ellipsis = "…" * cn_dots_count
    
    logging.debug(f"原文省略号密度: {dots_count}个点 -> 转换为{cn_dots_count}个中文点 -> {chinese_ellipsis}")
    return chinese_ellipsis

def fix_punctuation_in_file(file_path):
    """修复单个文件中的标点符号问题"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 先统计需要替换的数量
        replacements_needed = 0
        
        # 更新正则表达式以支持多行消息和多个段落
        # 使用re.DOTALL标志使 . 也能匹配换行符
        message_pattern = r'(\[message [^\]]*text=)(.*?)(\])'
        messages = re.finditer(message_pattern, content, re.DOTALL)
        
        for message_match in messages:
            message_text = message_match.group(2)
            # 在消息文本中查找所有 <r\=原文>译文</r> 段落
            segment_pattern = r'(<r\\=)([^>]*)(>)(.*?)(<\/r>)'
            segments = re.finditer(segment_pattern, message_text, re.DOTALL)
            
            for segment_match in segments:
                original_text = segment_match.group(2)  # 原文
                translated_text = segment_match.group(4)  # 译文
                
                # 检查原文和译文中是否有省略号需要替换
                if (re.search(r'\.{2,}|…+|\.\.+|。{2,}', original_text) or 
                    re.search(r'\.{2,}|…+|\.\.+|。{2,}', translated_text)):
                    replacements_needed += 1
        
        # 如果不需要替换，直接返回
        if replacements_needed == 0:
            logging.info(f"文件 {file_path} 无需修改")
            return False
        
        # 创建一个新的内容副本进行修改
        modified_content = content
        
        # 替换函数
        def replace_in_message(message_match):
            prefix = message_match.group(1)
            message_text = message_match.group(2)
            suffix = message_match.group(3)
            
            # 在消息文本中查找并替换所有 <r\=原文>译文</r> 段落
            def replace_in_segment(segment_match):
                segment_prefix = segment_match.group(1)  # <r\=
                original_text = segment_match.group(2)    # 原文
                middle = segment_match.group(3)           # >
                translated_text = segment_match.group(4)  # 译文
                segment_suffix = segment_match.group(5)   # </r>
                
                # 检查原文中是否有省略号
                has_original_ellipsis = re.search(r'\.{2,}|…+|\.\.+|。{2,}', original_text)
                has_translated_ellipsis = re.search(r'\.{2,}|…+|\.\.+|。{2,}', translated_text)
                
                # 如果原文和译文都没有省略号，不需要替换
                if not has_original_ellipsis and not has_translated_ellipsis:
                    return segment_prefix + original_text + middle + translated_text + segment_suffix
                
                # 记录替换前的文本用于调试
                original_text_copy = original_text
                translated_text_copy = translated_text
                
                # 如果原文中有省略号，根据原文省略号的密度来确定要使用的中文省略号
                if has_original_ellipsis:
                    chinese_ellipsis = count_ellipsis_density(original_text)
                    
                    # 替换译文中的所有省略号形式为对应密度的中文省略号
                    if has_translated_ellipsis:
                        translated_text = re.sub(r'\.{2,}|…+|\.\.+|。{2,}', chinese_ellipsis, translated_text)
                else:
                    # 如果原文中没有省略号但译文中有，使用默认的中文省略号
                    translated_text = re.sub(r'\.{2,}', '……', translated_text)
                    translated_text = re.sub(r'…+', '……', translated_text)
                    translated_text = re.sub(r'\.\.+', '……', translated_text)
                    translated_text = re.sub(r'。{2,}', '……', translated_text)
                
                # 如果替换成功
                if translated_text_copy != translated_text:
                    logging.debug(f"替换: '{translated_text_copy}' -> '{translated_text}'")
                
                return segment_prefix + original_text + middle + translated_text + segment_suffix
            
            # 使用re.DOTALL标志使 . 也能匹配换行符
            new_message_text = re.sub(r'(<r\\=)([^>]*)(>)(.*?)(<\/r>)', replace_in_segment, message_text, flags=re.DOTALL)
            return prefix + new_message_text + suffix
        
        # 使用re.DOTALL标志使 . 也能匹配换行符
        modified_content = re.sub(message_pattern, replace_in_message, content, flags=re.DOTALL)
        
        # 如果内容有变化，写回文件
        if content != modified_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            logging.info(f"已修复文件 {file_path}: 替换了省略号为标准的中文省略号")
            return True
        else:
            logging.info(f"文件 {file_path} 无需修改")
            return False
    except Exception as e:
        logging.error(f"处理文件 {file_path} 时出错: {e}")
        return False

def process_all_files(directory):
    """处理目录下所有txt文件中的省略号问题"""
    data_dir = Path(directory)
    if not data_dir.exists() or not data_dir.is_dir():
        logging.error(f"目录 {directory} 不存在或不是一个有效的目录")
        return
    
    fixed_files = 0
    processed_files = 0
    
    # 递归获取所有txt文件
    for txt_file in data_dir.glob('**/*.txt'):
        processed_files += 1
        if fix_punctuation_in_file(txt_file):
            fixed_files += 1
        
        # 每处理100个文件打印一次进度
        if processed_files % 100 == 0:
            logging.info(f"已处理 {processed_files} 个文件，修复了 {fixed_files} 个文件")
    
    logging.info(f"全部处理完成！共处理 {processed_files} 个文件，修复了 {fixed_files} 个文件")

# 添加一个函数用于检查特定文件的省略号问题
def check_specific_file(file_path):
    """检查特定文件中的省略号问题并修复"""
    file_path = Path(file_path)
    if not file_path.exists():
        logging.error(f"文件 {file_path} 不存在")
        return
    
    logging.info(f"开始检查特定文件: {file_path}")
    if fix_punctuation_in_file(file_path):
        logging.info(f"文件 {file_path} 已修复")
    else:
        logging.info(f"文件 {file_path} 不需要修复或修复失败")

if __name__ == "__main__":
    import sys
    
    # 默认处理当前目录下的data文件夹
    data_directory = "data"
    
    # 如果命令行参数有两个及以上，认为第一个是命令，第二个是路径
    if len(sys.argv) >= 3 and sys.argv[1] == "check":
        # 检查特定文件
        logging.info(f"开始检查特定文件 {sys.argv[2]}")
        check_specific_file(sys.argv[2])
    elif len(sys.argv) > 1:
        # 如果命令行提供了目录，则使用命令行参数
        data_directory = sys.argv[1]
        logging.info(f"开始处理目录 {data_directory} 下的文件")
        process_all_files(data_directory)
    else:
        logging.info(f"开始处理目录 {data_directory} 下的文件")
        process_all_files(data_directory)