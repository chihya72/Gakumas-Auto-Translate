"""
工具模块，包含共享的实用函数
"""

import os
import re
import json
import pandas as pd

def create_sample_dictionary(dict_file):
    """创建一个示例字典文件"""
    sample_dict = {
        "ことね": "琴音",
        "リーリヤ": "莉莉娅",
        "広": "广"
    }
    
    # 确保目录存在
    os.makedirs(os.path.dirname(dict_file), exist_ok=True)
    
    # 写入示例字典
    with open(dict_file, 'w', encoding='utf-8') as f:
        json.dump(sample_dict, f, ensure_ascii=False, indent=4)

def clean_html_tags(text):
    """清理文本中的HTML样式标签，只保留标签内的内容"""
    if text is None:
        return text
    # 匹配 <r\=...>内容</r> 只取内容
    text = re.sub(r'<r\\=[^>]+>(.*?)</r>', r'\1', text)
    # 再处理 <em\=...>内容</em>
    text = re.sub(r'<em\\=[^>]*>(.*?)</em>', r'\1', text)
    # 处理 <em>内容</em>
    text = re.sub(r'<em>(.*?)</em>', r'\1', text)
    return text

def remove_r_tags_inplace(csv_path):
    """移除文本中的r标签并保存回原文件"""
    df = pd.read_csv(csv_path, dtype=str)
    def clean_text(text):
        if pd.isnull(text):
            return text
        return clean_html_tags(text)
    df['text'] = df['text'].apply(clean_text)
    df.to_csv(csv_path, index=False, encoding='utf-8')

def ensure_dir_exists(dir_path):
    """确保目录存在，如不存在则创建"""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"已创建目录: {dir_path}")
        return True
    return False

def process_unit_text(text):
    """处理文本中特定标签，用于adv_unit_开头的文件
    
    如果文本以[narration text=或[message text=开头，
    则去除含有'―'属性的r标签，但保留标签内容
    """
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

def process_unit_file(file_path):
    """处理单个adv_unit_开头的文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = [process_unit_text(line) for line in lines]
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f'已处理文件: {file_path}')
        return True
    except Exception as e:
        print(f'处理文件失败 {file_path}: {str(e)}')
        return False

def process_unit_files_in_folder(folder_path):
    """处理文件夹中所有adv_unit_开头的txt文件"""
    processed_count = 0
    for file in os.listdir(folder_path):
        if file.startswith('adv_unit_') and file.endswith('.txt'):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path):
                if process_unit_file(file_path):
                    processed_count += 1
    
    if processed_count > 0:
        print(f"已处理 {processed_count} 个 adv_unit_ 文件")
    else:
        print("未找到需要处理的 adv_unit_ 文件")
    
    return processed_count