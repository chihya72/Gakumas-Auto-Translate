"""
预处理模块，用于预处理待翻译文本和人名替换
"""

import os
import re
import csv
import json
import shutil
from pathlib import Path
from .utils import remove_r_tags_inplace

def preprocess_txt_files():
    """预处理待翻译的txt文件（包含message、choice和narration）"""
    source_dir = "./todo/untranslated/txt"
    output_dir = "./todo/untranslated/csv_orig"
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 常见编码列表，按尝试顺序排列
    encodings_to_try = ['utf-8', 'shift-jis', 'gbk', 'cp932', 'latin1', 'cp1252']
    
    for filename in os.listdir(source_dir):
        if not filename.endswith(".txt"):
            continue
            
        input_path = os.path.join(source_dir, filename)
        output_path = os.path.join(output_dir, filename.replace(".txt", ".csv"))
        
        extracted_data = []
        
        # 尝试不同的编码格式
        file_content = None
        
        for encoding in encodings_to_try:
            try:
                with open(input_path, 'r', encoding=encoding) as f:
                    file_content = f.readlines()
                print(f"成功使用 {encoding} 编码读取文件: {filename}")
                break
            except UnicodeDecodeError:
                continue
        
        if file_content is None:
            print(f"无法识别文件编码格式，跳过文件: {filename}")
            continue
            
        for line in file_content:
            line = line.strip()
              # 匹配message类型
            message_match = re.match(r'\[message text=(.*?)\s*name=([^\s]+)', line)
            if message_match:
                text_content = message_match.group(1).strip('"')
                name_content = message_match.group(2).split()[0].strip('"')
                extracted_data.append({
                    'id': '0000000000000',
                    'name': name_content,
                    'text': text_content,
                    'trans': ''
                })
                continue
            
            # 匹配choices类型
            choices_match = re.findall(r'choice text=([^]]+?)\]', line)
            if choices_match:
                for choice_text in choices_match:
                    clean_text = choice_text.strip('"')
                    extracted_data.append({
                        'id': 'select',
                        'name': '',
                        'text': clean_text,
                        'trans': ''
                    })
                    continue
            
            # 匹配narration类型
            narration_match = re.match(r'\[narration text=([^\s"\']+)', line)
            if narration_match:
                text_content = narration_match.group(1).strip('"')
                extracted_data.append({
                    'id': 'narration',
                    'name': '__narration__',
                    'text': text_content,
                    'trans': ''
                })
                continue
        
        # 记录添加info行前的数据量
        original_length = len(extracted_data)
        # 添加info行到列表末尾
        extracted_data.append({
            'id': 'info',
            'name': filename,
            'text': '',
            'trans': ''
        })
        
        # 仅当存在有效数据时才生成CSV文件
        if original_length > 0:
            # 写入CSV文件
            with open(output_path, 'w', encoding='utf-8', newline='') as csvfile:
                fieldnames = ['id', 'name', 'text', 'trans']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                for row in extracted_data:
                    writer.writerow(row)

            print(f"已生成预处理文件: {output_path}")

            # （1）先复制到csv_dict
            dict_output_path = output_path.replace("csv_orig", "csv_dict")
            shutil.copy2(output_path, dict_output_path)
            print(f"已复制到词典替换目录: {dict_output_path}")

            # （2）然后在dict文件中清理标签
            remove_r_tags_inplace(dict_output_path)
            print(f"已去除<\\r=></r>标签: {dict_output_path}")
        else:
            print(f"跳过文件 {filename}，未找到可翻译内容")
    
    # 预处理完成后，立即进行字典替换
    print("\n正在执行字典替换...")
    replace_names_in_csv()
    return True


def replace_names_in_csv():
    """使用字典替换CSV文件中的人名和常见称谓"""
    # 定义路径常量
    csv_dir = "./todo/untranslated/csv_dict"
    dict_file = "./name_dictionary.json"
    
    # 检查字典文件是否存在
    if not os.path.exists(dict_file):
        print(f"未找到字典文件: {dict_file}")
        print("跳过字典替换步骤")
        return False
    
    # 加载字典文件
    try:
        with open(dict_file, 'r', encoding='utf-8') as f:
            name_dict = json.load(f)
            print(f"已加载字典，包含 {len(name_dict)} 个替换项")
    except Exception as e:
        print(f"加载字典文件时出错: {e}")
        return False
    
    # 检查是否有CSV文件
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    if not csv_files:
        print("没有找到需要处理的CSV文件")
        return False
    
    # 处理所有CSV文件
    processed_count = 0
    replaced_count = 0
    
    for filename in csv_files:
        file_path = os.path.join(csv_dir, filename)
        
        # 读取CSV文件
        rows = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        
        # 遍历每一行进行替换
        file_replaced = 0
        for row in rows:
            original_text = row['text']
            
            # 对文本进行替换
            replaced_text = original_text
            for jp_term, cn_term in name_dict.items():
                # 使用正则表达式确保完整匹配词语
                replaced_text = re.sub(r'\b' + re.escape(jp_term) + r'\b', cn_term, replaced_text)
                
                # 也检查不带词边界的情况（对日文可能更合适）
                if jp_term in replaced_text:
                    replaced_text = replaced_text.replace(jp_term, cn_term)
            
            # 如果有替换，更新文本
            if replaced_text != original_text:
                row['text'] = replaced_text
                file_replaced += 1
        
        # 只有在有实际替换时才写回文件
        if file_replaced > 0:
            with open(file_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            
            processed_count += 1
            replaced_count += file_replaced
            print(f"处理文件 {filename}: 替换了 {file_replaced} 处内容")
    
    # 输出处理摘要
    if processed_count > 0:
        print(f"\n完成替换！处理了 {processed_count} 个文件，共替换 {replaced_count} 处内容")
        return True
    else:
        print("\n未发现需要替换的内容")
        return False