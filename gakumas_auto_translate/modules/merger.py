"""
合并模块，处理翻译文件的合并功能
"""

import os
import re
import csv
import json
import shutil
from .utils import clean_html_tags  # 导入通用的HTML标签清理函数

def merge_translations():
    """合并翻译文件的主函数"""
    # 步骤1: 检查目录文件一致性
    gakumas_translated_dir = "./GakumasPreTranslation/tmp/translated"
    gakumas_untranslated_dir = "./GakumasPreTranslation/tmp/untranslated"
    
    # 检查目录是否存在
    if not os.path.exists(gakumas_translated_dir) or not os.path.exists(gakumas_untranslated_dir):
        print("错误：Gakumas翻译目录不存在，请先完成翻译流程")
        return False
    
    # 获取两个目录的CSV文件列表
    translated_files = set(f for f in os.listdir(gakumas_translated_dir) if f.endswith(".csv"))
    untranslated_files = set(f for f in os.listdir(gakumas_untranslated_dir) if f.endswith(".csv"))
    
    # 比较文件集合
    if translated_files != untranslated_files:
        print("错误：翻译目录文件不一致")
        print(f"未翻译目录文件: {untranslated_files - translated_files}")
        print(f"多余翻译文件: {translated_files - untranslated_files}")
        return False
    
    # 步骤2: 复制CSV文件到临时目录
    target_csv_dir = "./todo/translated/csv"
    os.makedirs(target_csv_dir, exist_ok=True)
    
    print("正在复制翻译后的CSV文件...")
    for filename in translated_files:
        src = os.path.join(gakumas_translated_dir, filename)
        dst = os.path.join(target_csv_dir, filename)
        shutil.copy2(src, dst)
        print(f"已复制: {filename}")
    
    # 步骤3: 修复使用原始未替换的text字段
    csv_orig_dir = "./todo/untranslated/csv_orig"  # 使用csv_orig目录
    
    print("\n正在恢复原始text字段，保留翻译结果...")
    for filename in translated_files:
        # 获取原始未替换的文本
        orig_csv_path = os.path.join(csv_orig_dir, filename)
        translated_csv_path = os.path.join(target_csv_dir, filename)
        
        if not os.path.exists(orig_csv_path):
            print(f"警告: 找不到原始文件 {filename}")
            continue
            
        # 读取原始未替换的文本
        orig_rows = []
        with open(orig_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            orig_rows = list(reader)
            
        # 读取翻译后的文本
        trans_rows = []
        with open(translated_csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            trans_rows = list(reader)
            
        # 检查文件的行数
        # 处理译者信息行：翻译文件可能在最后添加了一行译者信息
        has_translator_row = False
        translator_info = None
        if len(trans_rows) > len(orig_rows):
            # 检查最后一行是否为译者信息行
            last_row = trans_rows[-1]
            if 'id' in last_row and last_row['id'] == '译者':
                has_translator_row = True
                # 移除译者行以进行常规比较和处理
                translator_info = trans_rows.pop()
                print(f"检测到译者信息行: {translator_info['id']},{translator_info.get('name', '')}")
            
        # 再次检查行数是否一致
        if len(orig_rows) != len(trans_rows):
            print(f"警告: 文件 {filename} 行数不一致（原始: {len(orig_rows)}, 翻译: {len(trans_rows)}），跳过处理")
            continue
            
        # 将原始text字段复制到翻译后的文件中
        changes = 0
        for i, (orig_row, trans_row) in enumerate(zip(orig_rows, trans_rows)):
            if orig_row['id'] == trans_row['id'] and orig_row['text'] != trans_row['text']:
                trans_row['text'] = orig_row['text']  # 使用原始text字段
                changes += 1
                
        # 重新添加译者行（如果存在）
        if has_translator_row and translator_info:
            trans_rows.append(translator_info)
        
        # 保存更新后的翻译文件
        with open(translated_csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=trans_rows[0].keys())
            writer.writeheader()
            writer.writerows(trans_rows)
        
        if changes > 0:
            print(f"已更新文件 {filename}: 恢复了 {changes} 处原始text字段")
        else:
            print(f"文件 {filename} 无需更新text字段")
    
    # 步骤4: 用户选择合并模式
    while True:
        print("\n请选择合并模式:")
        print("1. 纯中文（仅保留翻译内容）")
        print("2. 中日双语（保留原文和翻译）")
        choice = input("请输入选项(1/2): ").strip()
        
        if choice == '1':
            process_pure_chinese()
            return True
        elif choice == '2':
            process_bilingual()
            return True
        else:
            print("无效输入，请重新选择")


def process_pure_chinese():
    """纯中文替换逻辑（包含narration处理）"""
    csv_dir = "./todo/translated/csv"
    untranslated_txt_dir = "./todo/untranslated/txt"
    output_dir = "./todo/translated/txt"
    dict_file = "./name_dictionary.json"
    
    # 加载名称字典
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
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取CSV文件列表
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    
    for csv_file in csv_files:
        # 构造文件路径
        csv_path = os.path.join(csv_dir, csv_file)
        txt_file = csv_file.replace(".csv", ".txt")
        txt_path = os.path.join(untranslated_txt_dir, txt_file)
        output_path = os.path.join(output_dir, txt_file)
        
        # 检查原始TXT文件是否存在
        if not os.path.exists(txt_path):
            print(f"警告：跳过 {csv_file}，未找到对应的原始TXT文件")
            continue
        
        # 读取CSV内容
        rows = []
        orig_texts = []
        trans_texts = []
        names = []  # 添加保存name的列表
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row['id'])
                orig_texts.append(row['text'])
                trans_texts.append(row['trans'])
                names.append(row['name'] if 'name' in row else '')  # 保存name值
        
        # 读取原始文本内容
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 进行文本替换
        for i, (row_id, orig, trans, name) in enumerate(zip(rows, orig_texts, trans_texts, names)):
            if not orig:
                continue
            
            # 清理原文中可能存在的标签，保持一致性
            clean_orig = clean_html_tags(orig)
        
            if row_id == 'choice':
                # 处理choice类型
                pattern = re.compile(
                    r'(choice text=)(["\']?)%s\2' % re.escape(clean_orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
    
            elif row_id == 'message':
                # 处理message类型
                pattern = re.compile(
                    r'(text=)(["\']?)%s\2' % re.escape(clean_orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)

            elif row_id == 'narration':  # 处理narration
                pattern = re.compile(
                    r'(narration text=)(["\']?)%s\2' % re.escape(clean_orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
                
                # 也匹配可能的text属性
                pattern = re.compile(
                    r'(text=)(["\']?)%s\2' % re.escape(clean_orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
                
            # 增加：翻译name属性
            if name and name_dict:
                translated_name = name
                for jp_name, cn_name in name_dict.items():
                    if jp_name == name:
                        translated_name = cn_name
                        break
                    
                if translated_name != name:
                    # 替换name属性
                    name_pattern = re.compile(
                        r'(name=)(["\']?)%s\2' % re.escape(name),
                        flags=re.IGNORECASE
                    )
                    content = name_pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{translated_name}{m.group(2)}', content)
        
        # 写入新文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已生成纯中文文件: {output_path}")

    print("\n合并完成！请检查以下目录:")
    print(f"- 翻译结果: {os.path.abspath(output_dir)}")
    print("下一步建议:")
    print("1. 手动检查合并结果")
    print("2. 将最终文件复制回游戏目录")


def process_bilingual():
    """处理中日双语合并逻辑"""
    # 定义路径常量
    csv_dir = "./todo/translated/csv"
    untranslated_txt_dir = "./todo/untranslated/txt"
    output_dir = "./todo/translated/txt"
    dict_file = "./name_dictionary.json"
    
    # 加载名称字典
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
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取CSV文件列表
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    
    for csv_file in csv_files:
        # 构造文件路径
        csv_path = os.path.join(csv_dir, csv_file)
        txt_file = csv_file.replace(".csv", ".txt")
        txt_path = os.path.join(untranslated_txt_dir, txt_file)
        output_path = os.path.join(output_dir, txt_file)
        
        # 检查原始TXT文件是否存在
        if not os.path.exists(txt_path):
            print(f"警告：跳过 {csv_file}，未找到对应的原始TXT文件")
            continue
        
        # 读取CSV内容
        rows = []
        orig_texts = []
        trans_texts = []
        names = []  # 添加保存name的列表
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row['id'])
                orig_texts.append(row['text'])
                trans_texts.append(row['trans'])
                names.append(row['name'] if 'name' in row else '')  # 保存name值
        
        # 读取原始文本内容
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 进行文本替换
        for i, (row_id, orig, trans, name) in enumerate(zip(rows, orig_texts, trans_texts, names)):
            if not orig:
                continue
            
            # 使用通用函数清理原文中的标签
            clean_orig = clean_html_tags(orig)
        
            if row_id == 'choice':
                # 处理choice类型
                pattern = re.compile(
                    r'(choice text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
    
            elif row_id == 'message':
                parts = clean_orig.split("\\n")
                trans_parts = trans.split("\\n")
    
                bilingual_text = ""
                for i, (part, trans_part) in enumerate(zip(parts, trans_parts)):
                    if i < len(parts) - 1:
                        bilingual_text += f"<r\\={part}>{trans_part}</r>\\r\\n"
                    else:
                        bilingual_text += f"<r\\={part}>{trans_part}</r>"
    
                pattern = re.compile(
                    r'(text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)

            elif row_id == 'narration':  # 处理narration
                parts = clean_orig.split("\\n")
                trans_parts = trans.split("\\n")
                bilingual_text = "".join(
                    [f"<r\\={p}>{tp}</r>\\r\\n" 
                     for p, tp in zip(parts, trans_parts)]
                ).rstrip('\\r\\n')
                
                pattern = re.compile(
                    r'(narration text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)
                
                # 替换原始内容中的 text 部分
                pattern = re.compile(
                    r'(text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)

            # 增加：翻译name属性
            if name and name_dict:
                translated_name = name
                for jp_name, cn_name in name_dict.items():
                    if jp_name == name:
                        translated_name = cn_name
                        break
                    
                if translated_name != name:
                    # 替换name属性
                    name_pattern = re.compile(
                        r'(name=)(["\']?)%s\2' % re.escape(name),
                        flags= re.IGNORECASE
                    )
                    content = name_pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{translated_name}{m.group(2)}', content)
        
        # 写入新文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已生成中日双语文件: {output_path}")

    print("\n合并完成！请检查以下目录:")
    print(f"- 翻译结果: {os.path.abspath(output_dir)}")
    print("下一步建议:")
    print("1. 手动检查合并结果")
    print("2. 将最终文件复制回游戏目录")