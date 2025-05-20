"""
预处理模块，用于预处理待翻译文本和人名替换
"""

import os
import re
import csv
import json
import shutil
from pathlib import Path
from .utils import remove_r_tags_inplace, clean_html_tags

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
            narration_match = re.match(r'\[\[?narration text=(.*?)(?:\]|\s+\w+=)', line)
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

    # 在字典替换后，对csv_dict中的所有CSV文件进行HTML标签清理
    print("\n正在清理CSV文件中的HTML标签...")
    clean_html_in_csv_dict() # 新增调用

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
        fieldnames = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                rows = list(reader)
        except Exception as e:
            print(f"读取CSV文件 {filename} 时出错: {e}")
            continue
        
        if not rows or not fieldnames: # 确保读取成功且文件非空
            print(f"跳过空文件或读取失败的文件: {filename}")
            continue
            
        # 遍历每一行进行替换
        file_replaced_by_dict = 0 # 记录字典替换次数
        for row in rows:
            original_text = row.get('text', '')
            if not isinstance(original_text, str): # 确保text字段是字符串
                original_text = str(original_text)
            
            # 对文本进行替换
            replaced_text = original_text
            for jp_term, cn_term in name_dict.items():
                # 使用正则表达式确保完整匹配词语
                # 注意: re.sub如果找不到匹配，会返回原字符串，所以不需要 pre-check jp_term in replaced_text
                replaced_text = re.sub(r'\b' + re.escape(jp_term) + r'\b', cn_term, replaced_text)
                
                # 也检查不带词边界的情况（对日文可能更合适）
                # 确保先进行带边界的替换，再进行不带边界的，避免部分替换问题
                # 或者根据实际需求调整这里的逻辑，例如只用一种或根据字典项特性选择
                if jp_term in replaced_text: # 再次检查是为了处理第一次re.sub可能未覆盖的情况
                    replaced_text = replaced_text.replace(jp_term, cn_term)
            
            # 如果有替换，更新文本
            if replaced_text != original_text:
                row['text'] = replaced_text
                file_replaced_by_dict += 1
        
        # 只有在有实际字典替换时才写回文件
        if file_replaced_by_dict > 0:
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                
                processed_count += 1
                replaced_count += file_replaced_by_dict
                print(f"处理文件 {filename} (字典替换): 替换了 {file_replaced_by_dict} 处内容")
            except Exception as e:
                print(f"写入CSV文件 {filename} (字典替换后) 时出错: {e}")

    # 输出处理摘要
    if processed_count > 0:
        print(f"\n完成字典替换！处理了 {processed_count} 个文件，共替换 {replaced_count} 处内容")
    else:
        print("\n未发现需要字典替换的内容")
    return True # 字典替换本身无论是否替换都算完成


def clean_html_in_csv_dict():
    """清理csv_dict目录下所有CSV文件text列的HTML标签"""
    csv_dir = "./todo/untranslated/csv_dict"
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]

    if not csv_files:
        print("在 {csv_dir} 中没有找到需要清理HTML标签的CSV文件")
        return False

    cleaned_files_count = 0
    total_lines_cleaned = 0

    for filename in csv_files:
        file_path = os.path.join(csv_dir, filename)
        rows = []
        fieldnames = []
        original_content_for_comparison = [] # 用于比较是否有实际内容变化
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                if not fieldnames: # 处理空CSV或无表头的情况
                    print(f"跳过文件 {filename}，无表头或为空。")
                    continue
                for row in reader:
                    rows.append(dict(row)) # 创建副本，避免修改影响迭代器
                    original_content_for_comparison.append(dict(row)) # 存储原始行用于比较

        except Exception as e:
            print(f"读取CSV文件 {filename} (HTML清理前) 时出错: {e}")
            continue

        if not rows:
            print(f"文件 {filename} 为空或读取失败，跳过HTML清理。")
            continue

        lines_cleaned_in_file = 0
        file_content_changed = False

        for i, row in enumerate(rows):
            original_text = row.get('text', '')
            if not isinstance(original_text, str):
                 original_text = str(original_text)

            cleaned_text = clean_html_tags(original_text)

            if cleaned_text != original_text:
                row['text'] = cleaned_text
                lines_cleaned_in_file += 1
                file_content_changed = True
        
        if file_content_changed: # 只有当文件内容因HTML清理而改变时才写回
            try:
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                print(f"处理文件 {filename} (HTML清理): 清理了 {lines_cleaned_in_file} 行的HTML标签")
                cleaned_files_count += 1
                total_lines_cleaned += lines_cleaned_in_file
            except Exception as e:
                print(f"写入CSV文件 {filename} (HTML清理后) 时出错: {e}")
        else:
            print(f"文件 {filename} (HTML清理): 无需清理HTML标签或内容未改变")

    if cleaned_files_count > 0:
        print(f"\n完成HTML标签清理！处理了 {cleaned_files_count} 个文件，共清理了 {total_lines_cleaned} 行的HTML标签。")
    else:
        print("\n未发现需要清理HTML标签的内容，或内容清理后未发生变化。")
    return True