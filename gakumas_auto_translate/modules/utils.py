"""
工具模块，包含文本处理、文件操作和字典管理等共享实用函数
"""

import os
import re
import json
import pandas as pd
import csv

def create_sample_dictionary(dict_file):
    """
    创建一个示例名称字典文件
    
    在指定路径创建一个包含基本日中人名映射的JSON格式字典文件，
    主要用于初始化项目或示例用途。
    
    Args:
        dict_file (str): 字典文件的保存路径
    """
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
    """
    清理文本中的HTML样式标签，只保留标签内的内容
    
    处理游戏中特定的标签格式，如<r\=...>内容</r>和<em\=...>内容</em>，
    移除标签但保留标签内的文本内容。
    
    Args:
        text (str): 需要清理标签的原始文本
        
    Returns:
        str: 清理标签后的文本，如果输入为None则返回None
    """
    if text is None:
        return text
    # 匹配 <r\=...>内容</r> 只取内容
    text = re.sub(r'<r\\=[^>]+>(.*?)</r>', r'\1', text)
    # 再处理 <em\=...>内容</em>
    text = re.sub(r'<em\\=[^>]*>(.*?)</em>', r'\1', text)
    return text

def remove_r_tags_inplace(csv_path):
    """
    移除CSV文件中文本字段的r标签并直接保存回原文件
    
    读取CSV文件，清理'text'列中的HTML标签，然后将处理后的数据保存回原文件。
    
    Args:
        csv_path (str): CSV文件的路径
    """
    df = pd.read_csv(csv_path, dtype=str)
    def clean_text(text):
        if pd.isnull(text):
            return text
        return clean_html_tags(text)
    df['text'] = df['text'].apply(clean_text)
    df.to_csv(csv_path, index=False, encoding='utf-8')

def ensure_dir_exists(dir_path):
    """
    确保目录存在，如不存在则创建
    
    检查指定路径的目录是否存在，如不存在则创建该目录及其所有父目录。
    
    Args:
        dir_path (str): 需要确保存在的目录路径
        
    Returns:
        bool: 如创建了新目录返回True，目录已存在返回False
    """
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
        print(f"已创建目录: {dir_path}")
        return True
    return False

def process_unit_text(text):
    """
    处理adv_unit_开头文件中的特定标签格式
    
    专门针对以[narration text=或[message text=开头的文本，
    去除含有'―'属性的r标签，但保留标签内容，用于处理游戏中的特殊格式。
    
    Args:
        text (str): 需要处理的原始文本行
        
    Returns:
        str: 处理后的文本行
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

def load_name_dictionary(dict_file="./name_dictionary.json"):
    """
    加载名称字典文件用于人名翻译
    
    从指定路径加载JSON格式的名称字典，用于将日文人名转换为中文人名。
    如果文件不存在或加载失败，将返回空字典。
    
    Args:
        dict_file (str): 字典文件路径，默认为项目根目录下的name_dictionary.json
        
    Returns:
        dict: 加载的名称字典(日文名:中文名)，如果加载失败则返回空字典
    """
    name_dict = {}
    if os.path.exists(dict_file):
        try:
            with open(dict_file, 'r', encoding='utf-8') as f:
                name_dict = json.load(f)
                print(f"已加载字典，包含 {len(name_dict)} 个替换项")
        except Exception as e:
            print(f"加载字典文件时出错: {e}")
    else:
        print(f"字典文件不存在: {dict_file}，将跳过人名翻译")
    
    return name_dict

def translate_name_with_dict(name, name_dict):
    """
    使用字典进行人名翻译
    
    根据提供的名称字典查找并翻译日文人名为中文。
    如果字典中不存在对应的翻译，则返回原始名称。
    
    Args:
        name (str): 需要翻译的原始名称（日文）
        name_dict (dict): 名称翻译字典，键为日文名，值为中文名
    
    Returns:
        str: 翻译后的名称，如果没有找到翻译则返回原名称
    """
    if not name or not name_dict:
        return name
        
    translated_name = name
    for jp_name, cn_name in name_dict.items():
        if jp_name == name:
            translated_name = cn_name
            break
    
    return translated_name

def process_adv_unit_files(folder_path):
    """
    批量处理文件夹中所有adv_unit_开头的TXT文件
    
    遍历指定文件夹，处理所有以adv_unit_开头的TXT文件中的特殊标签，
    主要用于游戏中特定类型文件的后处理。
    
    Args:
        folder_path (str): 包含adv_unit_文件的文件夹路径
    
    Returns:
        int: 成功处理的文件数量
    """
    processed_count = 0
    for file in os.listdir(folder_path):
        if file.startswith('adv_unit_') and file.endswith('.txt'):
            file_path = os.path.join(folder_path, file)
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    new_lines = [process_unit_text(line) for line in lines]
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    processed_count += 1
                    print(f'已处理文件: {file}')
                except Exception as e:
                    print(f'处理文件失败 {file}: {str(e)}')
    
    if processed_count > 0:
        print(f"已处理 {processed_count} 个 adv_unit_ 文件")
    else:
        print("未找到需要处理的 adv_unit_ 文件")
    
    return processed_count

def read_csv_content(csv_path):
    """
    读取CSV文件内容，提取翻译相关字段
    
    读取翻译CSV文件，获取id(类型)、text(原文)、trans(译文)和name(名称)字段，
    用于后续的文本替换和处理。
    
    Args:
        csv_path (str): CSV文件路径
        
    Returns:
        tuple: (rows, orig_texts, trans_texts, names) 
               分别是行类型、原文、译文和名称的列表
    """
    rows = []
    orig_texts = []
    trans_texts = []
    names = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row['id'])
            orig_texts.append(row['text'])
            trans_texts.append(row['trans'])
            names.append(row['name'] if 'name' in row else '')
    
    return rows, orig_texts, trans_texts, names