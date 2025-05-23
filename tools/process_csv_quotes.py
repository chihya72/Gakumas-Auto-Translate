#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV文件引号处理脚本
处理csv_data目录下的CSV文件，将trans列中的""替换为中文引号""
"""

import os
import re
import glob

def parse_csv_line(line):
    """
    使用正则表达式解析CSV行，提取各个字段
    处理包含逗号和换行符的引号字段
    """
    if not line.strip():
        return []
    
    fields = []
    current_field = ""
    in_quotes = False
    i = 0
    
    while i < len(line):
        char = line[i]
        
        if char == '"':
            if in_quotes:
                # 检查是否是转义的引号 ("") 
                if i + 1 < len(line) and line[i + 1] == '"':
                    current_field += '""'
                    i += 2
                    continue
                else:
                    # 引号结束
                    in_quotes = False
            else:
                # 引号开始
                in_quotes = True
            current_field += char
        elif char == ',' and not in_quotes:
            # 字段分隔符
            fields.append(current_field)
            current_field = ""
        else:
            current_field += char
        
        i += 1
    
    # 添加最后一个字段
    if current_field or line.endswith(','):
        fields.append(current_field)
    
    return fields

def process_trans_field(trans_field):
    """
    处理trans字段（第四列），移除外层引号并替换内部的""为中文引号
    """
    if not trans_field:
        return trans_field
    
    # 移除外层双引号
    if trans_field.startswith('"') and trans_field.endswith('"'):
        # 移除外层引号
        inner_content = trans_field[1:-1]
        # 智能地将成对的""替换为中文左右引号
        processed_content = replace_double_quotes_with_chinese(inner_content)
        # 直接返回处理后的内容，不重新添加外层引号
        return processed_content
    else:
        # 如果没有外层引号，直接替换""
        return replace_double_quotes_with_chinese(trans_field)

def replace_double_quotes_with_chinese(text):
    """
    将文本中的""（双双引号）替换为中文的左右引号"和"
    """
    if not text:
        return text
    
    result = ""
    i = 0
    quote_is_opening = True  # 标记下一个引号是否为开始引号
    
    while i < len(text):
        if i < len(text) - 1 and text[i:i+2] == '""':
            # 遇到双双引号，替换为中文引号
            if quote_is_opening:
                result += '\u201c'  # 中文左引号 "
            else:
                result += '\u201d'  # 中文右引号 "
            quote_is_opening = not quote_is_opening  # 切换状态
            i += 2  # 跳过两个字符
        else:
            result += text[i]
            i += 1
    
    return result

def rebuild_csv_line(fields):
    """
    重新构建CSV行
    """
    return ','.join(fields)

def process_csv_file(file_path):
    """
    处理单个CSV文件
    """
    print(f"处理文件: {file_path}")
    
    # 读取原始文件内容
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.splitlines()
    modified_lines = []
    
    for line_num, line in enumerate(lines, 1):
        if not line.strip():
            modified_lines.append(line)
            continue
            
        # 解析CSV行
        fields = parse_csv_line(line)
        
        # 如果有4个或更多字段，处理trans列（第四列，索引3）
        if len(fields) >= 4:
            original_trans = fields[3]
            processed_trans = process_trans_field(fields[3])
            fields[3] = processed_trans
            
            # 如果trans字段有修改，记录日志
            if original_trans != processed_trans:
                print(f"  行 {line_num}: 修改 trans 字段")
                print(f"    原文: {original_trans}")
                print(f"    修改: {processed_trans}")
        
        # 重新构建行
        modified_line = rebuild_csv_line(fields)
        modified_lines.append(modified_line)
    
    # 写回文件
    modified_content = '\n'.join(modified_lines)
    if content.rstrip() != modified_content.rstrip():
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified_content)
        print(f"  文件已更新: {file_path}")
    else:
        print(f"  文件无需修改: {file_path}")

def main():
    """
    主函数，处理csv_data目录下的所有CSV文件
    """
    csv_dir = "csv_data"
    
    if not os.path.exists(csv_dir):
        print(f"错误: 目录 {csv_dir} 不存在")
        return
    
    # 获取所有CSV文件
    csv_files = glob.glob(os.path.join(csv_dir, "*.csv"))
    
    if not csv_files:
        print(f"在 {csv_dir} 目录中没有找到CSV文件")
        return
    
    print(f"找到 {len(csv_files)} 个CSV文件")
    print("=" * 50)
    
    # 处理每个文件
    for csv_file in sorted(csv_files):
        try:
            process_csv_file(csv_file)
            print("-" * 30)
        except Exception as e:
            print(f"处理文件 {csv_file} 时出错: {e}")
            print("-" * 30)
    
    print("处理完成!")

if __name__ == "__main__":
    main()
