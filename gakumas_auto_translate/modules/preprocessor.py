"""
预处理模块，用于预处理待翻译文本和人名替换
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import re
import csv
import json
import shutil
from pathlib import Path
from logger import get_logger
from paths import get_path, ensure_paths_exist
from utils import remove_r_tags_inplace, read_file_with_encoding

# 获取日志记录器
logger = get_logger("preprocessor")

def preprocess_txt_files():
    """预处理待翻译的txt文件（包含message、choice和narration）"""
    # 获取路径
    source_dir = get_path("todo_untranslated_txt")
    output_dir = get_path("todo_untranslated_csv_orig")
    
    # 确保输出目录存在
    ensure_paths_exist(["todo_untranslated_csv_orig", "todo_untranslated_csv_dict"])
    
    # 处理文件计数
    processed_count = 0
    skipped_count = 0
    
    # 获取文件列表
    try:
        file_list = os.listdir(source_dir)
    except FileNotFoundError:
        logger.error(f"源目录不存在: {source_dir}")
        return False
    except PermissionError:
        logger.error(f"无权限访问源目录: {source_dir}")
        return False
    except Exception as e:
        logger.error(f"读取源目录失败: {e}")
        return False
    
    # 筛选txt文件
    txt_files = [f for f in file_list if f.endswith(".txt")]
    if not txt_files:
        logger.warning(f"未找到需要处理的txt文件: {source_dir}")
        return False
    
    logger.info(f"找到 {len(txt_files)} 个txt文件待处理")
    
    for filename in txt_files:
        input_path = os.path.join(source_dir, filename)
        output_path = os.path.join(output_dir, filename.replace(".txt", ".csv"))
        
        extracted_data = []
        
        # 读取文件内容
        file_content, used_encoding = read_file_with_encoding(input_path)
        
        if file_content is None:
            logger.error(f"无法读取文件: {filename}")
            skipped_count += 1
            continue
            
        # 按行处理
        try:
            lines = file_content.splitlines()
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # 匹配message类型
                message_match = re.match(r'\[message text=(.*?)\s*name=([^\s]+)', line)
                if message_match:
                    try:
                        text_content = message_match.group(1).strip('"')
                        name_content = message_match.group(2).split()[0].strip('"')
                        extracted_data.append({
                            'id': '0000000000000',
                            'name': name_content,
                            'text': text_content,
                            'trans': ''
                        })
                        continue
                    except Exception as e:
                        logger.warning(f"处理message行失败: {line[:50]}... - {e}")
                
                # 匹配choices类型
                try:
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
                except Exception as e:
                    logger.warning(f"处理choice行失败: {line[:50]}... - {e}")
                
                # 匹配narration类型
                narration_match = re.match(r'\[narration text=([^\s"\']+)', line)
                if narration_match:
                    try:
                        text_content = narration_match.group(1).strip('"')
                        extracted_data.append({
                            'id': 'narration',
                            'name': '__narration__',
                            'text': text_content,
                            'trans': ''
                        })
                        continue
                    except Exception as e:
                        logger.warning(f"处理narration行失败: {line[:50]}... - {e}")
            
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
                try:
                    # 写入CSV文件
                    with open(output_path, 'w', encoding='utf-8', newline='') as csvfile:
                        fieldnames = ['id', 'name', 'text', 'trans']
                        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                        writer.writeheader()
                        for row in extracted_data:
                            writer.writerow(row)

                    logger.info(f"已生成预处理文件: {output_path}")
                    processed_count += 1

                    # （1）先复制到csv_dict
                    dict_output_path = output_path.replace("csv_orig", "csv_dict")
                    shutil.copy2(output_path, dict_output_path)
                    logger.info(f"已复制到词典替换目录: {dict_output_path}")

                    # （2）然后在dict文件中清理标签
                    remove_r_tags_inplace(dict_output_path)
                    logger.info(f"已去除<\\r=></r>标签: {dict_output_path}")
                except Exception as e:
                    logger.error(f"生成CSV文件失败 {output_path}: {e}")
                    skipped_count += 1
            else:
                logger.warning(f"跳过文件 {filename}，未找到可翻译内容")
                skipped_count += 1
                
        except Exception as e:
            logger.error(f"处理文件失败 {filename}: {e}")
            skipped_count += 1
    
    # 输出处理摘要
    logger.info(f"\n预处理完成: 成功处理 {processed_count} 个文件, 跳过 {skipped_count} 个文件")
    
    # 预处理完成后，立即进行字典替换
    if processed_count > 0:
        logger.info("\n正在执行字典替换...")
        replace_names_in_csv()
        return True
    else:
        logger.warning("没有成功处理任何文件，跳过字典替换")
        return False


def replace_names_in_csv():
    """使用字典替换CSV文件中的人名和常见称谓"""
    # 定义路径常量
    csv_dir = get_path("todo_untranslated_csv_dict")
    dict_file = get_path("dict_file")
    
    # 检查字典文件是否存在
    if not os.path.exists(dict_file):
        logger.warning(f"未找到字典文件: {dict_file}")
        logger.warning("跳过字典替换步骤")
        return False
    
    # 加载字典文件
    try:
        with open(dict_file, 'r', encoding='utf-8') as f:
            name_dict = json.load(f)
            logger.info(f"已加载字典，包含 {len(name_dict)} 个替换项")
    except json.JSONDecodeError:
        logger.error(f"字典文件格式错误: {dict_file}")
        return False
    except Exception as e:
        logger.error(f"加载字典文件时出错: {e}")
        return False
    
    # 检查是否有CSV文件
    try:
        csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    except FileNotFoundError:
        logger.error(f"CSV目录不存在: {csv_dir}")
        return False
    except PermissionError:
        logger.error(f"无权限访问CSV目录: {csv_dir}")
        return False
    except Exception as e:
        logger.error(f"读取CSV目录失败: {e}")
        return False
    
    if not csv_files:
        logger.warning("没有找到需要处理的CSV文件")
        return False
    
    # 处理所有CSV文件
    processed_count = 0
    replaced_count = 0
    
    for filename in csv_files:
        file_path = os.path.join(csv_dir, filename)
        
        try:
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
                    try:
                        pattern = r'\b' + re.escape(jp_term) + r'\b'
                        replaced_text = re.sub(pattern, cn_term, replaced_text)
                    except Exception:
                        # 如果正则表达式失败，尝试直接替换
                        pass
                    
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
                logger.info(f"处理文件 {filename}: 替换了 {file_replaced} 处内容")
        except Exception as e:
            logger.error(f"处理文件失败 {filename}: {e}")
    
    # 输出处理摘要
    if processed_count > 0:
        logger.info(f"\n完成替换！处理了 {processed_count} 个文件，共替换 {replaced_count} 处内容")
        return True
    else:
        logger.info("\n未发现需要替换的内容")
        return False
