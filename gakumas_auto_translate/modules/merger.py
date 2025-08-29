"""
合并模块，处理翻译文件的合并功能
"""

import os
import re
import csv
import json
import shutil
from .utils import clean_html_tags, process_unit_files_in_folder  # 添加导入
from .config import get_translation_mode  # 添加导入

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
    
    # 步骤4: 根据翻译模式执行不同的合并逻辑
    translation_mode = get_translation_mode()
    if translation_mode == "bilingual":
        print("\n正在执行中日双语合并模式...")
        process_bilingual()
    else:
        print("\n正在执行纯中文合并模式...")
        process_chinese_only()
    return True


def process_bilingual():
    """处理中日双语合并逻辑"""
    # 定义路径常量
    csv_dir = "./todo/translated/csv"
    untranslated_txt_dir = "./todo/untranslated/txt"
    output_dir = "./todo/translated/txt"
    dict_file = "./name_dictionary.json"
    error_report_file = "./error_report.csv" # 定义错误报告文件路径
    
    # 初始化错误记录
    has_errors = False
    error_rows = [['文件', 'ID', '错误类型', '原文', '翻译', '详细信息']] # 错误报告头部
    
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
            # 可以选择记录此警告为错误，但当前按跳过处理
            continue
        
        # 读取CSV内容
        replace_items = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                replace_items = list(reader)
        except Exception as e:
            print(f"错误: 读取文件 {csv_file} 时出错: {e}")
            error_rows.append([csv_file, "N/A", "文件读取错误", "", "", str(e)])
            has_errors = True
            continue # 跳过此文件
            
        # 按原文长度降序排序
        replace_items.sort(key=lambda x: len(x.get('text', '') or ""), reverse=True)
        
        # 读取原始文本内容
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"错误: 读取文件 {txt_file} 时出错: {e}")
            error_rows.append([csv_file, "N/A", "原始文件读取错误", "", "", str(e)])
            has_errors = True
            continue # 跳过此文件
            
        # 进行文本替换
        changes_count = 0 # 记录当前文件替换次数
        file_has_errors = False # 标记当前文件是否有错误
        
        for row in replace_items:
            row_id = row.get('id', '')
            orig = row.get('text', '')
            trans = row.get('trans', '')
            name = row.get('name', '')
            
            if not orig or not trans:
                # 根据用户需求，对不同ID的空条目进行区分处理
                if row_id == 'info' or row_id == '译者':
                    # ID为info，原文或翻译为空是正常情况，只跳过，不记录错误，也不打印警告
                    # print(f"警告: 文件 {csv_file} 中ID为 {row_id} 的条目原文或翻译为空，跳过处理") # 删除此行
                    # 不记录为错误
                    pass # 显式地什么都不做
                else:
                    # 其他ID，原文或翻译为空视为错误
                    print(f"错误: 文件 {csv_file} 中ID为 {row_id} 的条目原文或翻译为空")
                    error_rows.append([csv_file, row_id, "条目内容不完整", orig, trans, "原文或翻译为空"])
                    has_errors = True
                    file_has_errors = True # 标记文件有错误

                continue # 跳过处理当前条目
            
            # 使用通用函数清理原文中的标签
            clean_orig = clean_html_tags(orig)
            
            # 临时存储当前替换后的内容，用于对比是否发生变化
            current_content = content
            
            if row_id == 'select':
                # 处理select类型 - 仅替换文本内容
                try:
                    # 修正正则表达式，不再匹配引号
                    pattern = re.compile(
                        r'(choice text=)%s' % re.escape(orig),
                    )
                    # 修正替换逻辑，不再处理引号
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{trans}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                except Exception as e:
                    print(f"处理文件 {csv_file} 中ID为 {row_id} 的select条目时出错: {e}")
                    error_rows.append([csv_file, row_id, "处理select错误", orig, trans, str(e)])
                    has_errors = True
                    file_has_errors = True

            elif row_id == '0000000000000':
                # 处理0000000000000类型 - 需要中日双语
                try:
                    # 移除原文末尾可能多余的 \n
                    processed_orig = clean_orig.rstrip('\\n')
                    # 分割处理后的原文和翻译为行
                    parts = processed_orig.split("\\n")
                    trans_parts = trans.split("\\n")
                    
                    # 检查原文和翻译的行数是否一致 (使用处理后的原文行数)
                    if len(parts) != len(trans_parts):
                        print(f"警告: 文件 {csv_file} 中ID为 {row_id} 的条目，原文和翻译的行数不一致 (原文: {len(parts)}行, 翻译: {len(trans_parts)}行)")
                        error_rows.append([
                            csv_file, row_id, "行数不匹配", 
                            processed_orig, trans, 
                            f"原文行数: {len(parts)}, 翻译行数: {len(trans_parts)}"
                        ])
                        has_errors = True
                        file_has_errors = True
                        continue  # 跳过处理此条目
                        
                    bilingual_text = "".join(
                        [f"<r\\={p}>{tp}</r>\\r\\n" 
                         for p, tp in zip(parts, trans_parts)]
                    ).rstrip('\\r\\n')
                    # 匹配 message text= 属性
                    pattern = re.compile(
                        r'(message text=)%s' % re.escape(orig),
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{bilingual_text}', content)
                    
                    # 检查是否发生替换并更新内容和计数
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                except Exception as e:
                    print(f"处理文件 {csv_file} 中ID为 {row_id} 的条目时出错: {e}")
                    error_rows.append([csv_file, row_id, "处理错误", processed_orig, trans, str(e)])
                    has_errors = True
                    file_has_errors = True
                    continue # 跳过处理此条目

            elif row_id == 'narration':  # 处理narration - 只保留中文翻译，不使用双语格式
                try:
                    # 匹配 narration text= 属性，直接替换为翻译
                    pattern = re.compile(
                        r'(narration text=)%s' % re.escape(orig),
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{trans}', content)
                    
                    # 检查是否发生替换并更新内容和计数
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                except Exception as e:
                    print(f"处理文件 {csv_file} 中ID为 {row_id} 的narration条目时出错: {e}")
                    error_rows.append([csv_file, row_id, "处理narration错误", orig, trans, str(e)])
                    has_errors = True
                    file_has_errors = True
                    continue # 跳过处理此条目

            # 翻译name属性 (无论row_id是什么类型)
            if name and name_dict:
                translated_name = name
                # 按照键长度从长到短排序，优先匹配较长的name
                found_name_translation = None
                for dict_name in sorted(name_dict.keys(), key=len, reverse=True):
                    if name == dict_name:
                        found_name_translation = name_dict[dict_name]
                        break
                
                if found_name_translation and translated_name != found_name_translation:
                    translated_name = found_name_translation
                
                if translated_name != name: # 如果找到了不同的翻译
                    try:
                        name_pattern = re.compile(
                            r'(name=)%s' % re.escape(name),
                        )
                        new_content = content # 使用临时变量进行替换，避免影响后续name替换
                        new_content = name_pattern.sub(lambda m: f'{m.group(1)}{translated_name}', new_content) # 直接替换name值，不加引号，因为name值通常没有引号

                        if new_content != content:
                            content = new_content
                            # 不增加 changes_count，因为它不是文本内容的替换
                    except Exception as e:
                         print(f"处理文件 {csv_file} 中ID为 {row_id} 的name属性时出错: {e}")
                         error_rows.append([csv_file, row_id, "处理name属性错误", name, translated_name, str(e)])
                         has_errors = True
                         file_has_errors = True

        # 如果文件处理过程中没有错误，则写入新文件
        if not file_has_errors:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"已生成中日双语文件: {output_path} (进行了 {changes_count} 处文本替换)")
            except Exception as e:
                print(f"错误: 写入文件 {output_path} 时出错: {e}")
                error_rows.append([csv_file, "N/A", "文件写入错误", "", "", str(e)])
                has_errors = True
        else:
            print(f"文件 {csv_file} 处理过程中存在错误，跳过生成输出文件")
    
    # 在处理完所有文件后调用 process_unit_files_in_folder (总是处理)
    print("\n正在处理adv_unit_开头的文件...")
    process_unit_files_in_folder(output_dir) # 无条件调用
    
    # 如果有错误，写入错误报告
    if has_errors:
        try:
            with open(error_report_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(error_rows)
            print(f"\n处理过程中发现错误，详细信息已保存到: {os.path.abspath(error_report_file)}")
        except Exception as e:
            print(f"错误: 写入错误报告时出错: {e}")
    
    print("\n合并完成！请检查以下目录:")
    print(f"- 翻译结果: {os.path.abspath(output_dir)}")
    if has_errors:
        print(f"- 错误报告: {os.path.abspath(error_report_file)}")
    else:
        print("未检测到处理错误。")


def process_chinese_only():
    """处理纯中文合并逻辑"""
    # 定义路径常量
    csv_dir = "./todo/translated/csv"
    untranslated_txt_dir = "./todo/untranslated/txt"
    output_dir = "./todo/translated/txt"
    dict_file = "./name_dictionary.json"
    error_report_file = "./error_report_chinese.csv" # 定义错误报告文件路径
    
    # 初始化错误记录
    has_errors = False
    error_rows = [['文件', 'ID', '错误类型', '原文', '翻译', '详细信息']] # 错误报告头部
    
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
        replace_items = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                replace_items = list(reader)
        except Exception as e:
            print(f"错误: 读取文件 {csv_file} 时出错: {e}")
            error_rows.append([csv_file, "N/A", "文件读取错误", "", "", str(e)])
            has_errors = True
            continue # 跳过此文件
            
        # 按原文长度降序排序
        replace_items.sort(key=lambda x: len(x.get('text', '') or ""), reverse=True)
        
        # 读取原始文本内容
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            print(f"错误: 读取文件 {txt_file} 时出错: {e}")
            error_rows.append([csv_file, "N/A", "原始文件读取错误", "", "", str(e)])
            has_errors = True
            continue # 跳过此文件
            
        # 进行文本替换
        changes_count = 0 # 记录当前文件替换次数
        file_has_errors = False # 标记当前文件是否有错误
        
        for row in replace_items:
            row_id = row.get('id', '')
            orig = row.get('text', '')
            trans = row.get('trans', '')
            name = row.get('name', '')
            
            if not orig or not trans:
                # 根据用户需求，对不同ID的空条目进行区分处理
                if row_id == 'info' or row_id == '译者':
                    # ID为info或译者，原文或翻译为空是正常情况，只跳过，不记录错误
                    pass
                else:
                    # 其他ID，原文或翻译为空视为错误
                    print(f"错误: 文件 {csv_file} 中ID为 {row_id} 的条目原文或翻译为空")
                    error_rows.append([csv_file, row_id, "条目内容不完整", orig, trans, "原文或翻译为空"])
                    has_errors = True
                    file_has_errors = True
                continue # 跳过处理当前条目
            
            # 纯中文模式：直接用翻译替换原文，不需要清理原文中的标签
            try:
                if row_id == 'select':
                    # 处理select类型 - 直接替换文本内容
                    pattern = re.compile(
                        r'(choice text=)%s' % re.escape(orig),
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{trans}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                elif row_id == '0000000000000':
                    # 处理message类型 - 直接替换
                    pattern = re.compile(
                        r'(message text=)%s' % re.escape(orig),
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{trans}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                elif row_id == 'narration':
                    # 处理narration类型 - 直接替换
                    pattern = re.compile(
                        r'(narration text=)%s' % re.escape(orig),
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{trans}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                        
            except Exception as e:
                print(f"处理文件 {csv_file} 中ID为 {row_id} 的条目时出错: {e}")
                error_rows.append([csv_file, row_id, "纯中文处理错误", orig, trans, str(e)])
                has_errors = True
                file_has_errors = True
                continue

            # 翻译name属性 (无论row_id是什么类型)
            if name and name_dict:
                translated_name = name
                # 按照键长度从长到短排序，优先匹配较长的name
                found_name_translation = None
                for dict_name in sorted(name_dict.keys(), key=len, reverse=True):
                    if name == dict_name:
                        found_name_translation = name_dict[dict_name]
                        break
                
                if found_name_translation and translated_name != found_name_translation:
                    translated_name = found_name_translation
                
                if translated_name != name: # 如果找到了不同的翻译
                    try:
                        name_pattern = re.compile(
                            r'(name=)%s' % re.escape(name),
                        )
                        new_content = name_pattern.sub(lambda m: f'{m.group(1)}{translated_name}', content)
                        if new_content != content:
                            content = new_content
                            # 不增加 changes_count，因为它不是文本内容的替换
                    except Exception as e:
                         print(f"处理文件 {csv_file} 中ID为 {row_id} 的name属性时出错: {e}")
                         error_rows.append([csv_file, row_id, "处理name属性错误", name, translated_name, str(e)])
                         has_errors = True
                         file_has_errors = True

        # 如果文件处理过程中没有错误，则写入新文件
        if not file_has_errors:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                print(f"已生成纯中文文件: {output_path} (进行了 {changes_count} 处文本替换)")
            except Exception as e:
                print(f"错误: 写入文件 {output_path} 时出错: {e}")
                error_rows.append([csv_file, "N/A", "文件写入错误", "", "", str(e)])
                has_errors = True
        else:
            print(f"文件 {csv_file} 处理过程中存在错误，跳过生成输出文件")
    
    # 在处理完所有文件后调用 process_unit_files_in_folder (总是处理)
    print("\n正在处理adv_unit_开头的文件...")
    process_unit_files_in_folder(output_dir) # 无条件调用
    
    # 如果有错误，写入错误报告
    if has_errors:
        try:
            with open(error_report_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(error_rows)
            print(f"\n处理过程中发现错误，详细信息已保存到: {os.path.abspath(error_report_file)}")
        except Exception as e:
            print(f"错误: 写入错误报告时出错: {e}")
    
    print("\n合并完成！请检查以下目录:")
    print(f"- 翻译结果: {os.path.abspath(output_dir)}")
    if has_errors:
        print(f"- 错误报告: {os.path.abspath(error_report_file)}")
    else:
        print("未检测到处理错误。")