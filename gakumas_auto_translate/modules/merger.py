"""
合并模块，处理翻译文件的合并功能
改进版：基于merger_updated_solution.py，并整合到新架构
"""

import os
import re
import csv
import json
import shutil
import pandas as pd
from datetime import datetime
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist

# 获取日志记录器
logger = get_logger("merger")

def process_bilingual():
    """处理中日双语合并逻辑 - 改进版"""
    # 定义路径常量
    csv_dir = get_path("todo_translated_csv")
    untranslated_txt_dir = get_path("todo_untranslated_txt")
    output_dir = get_path("todo_translated_txt")
    dict_file = get_path("dict_file")
    
    # 创建输出目录
    ensure_paths_exist(["todo_translated_txt"])
    
    # 创建错误报告文件，用于记录处理过程中出现的问题
    error_report_file = os.path.join(os.path.dirname(csv_dir), f"error_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
    error_rows = [["文件名", "ID类型", "问题类型", "原文", "译文", "详细信息"]]
    has_errors = False
    
    # 加载名称字典
    name_dict = {}
    if os.path.exists(dict_file):
        try:
            with open(dict_file, 'r', encoding='utf-8') as f:
                name_dict = json.load(f)
                logger.info(f"已加载字典，包含 {len(name_dict)} 个替换项")
        except Exception as e:
            logger.error(f"加载字典文件时出错: {e}")
    else:
        logger.warning(f"字典文件不存在: {dict_file}，将跳过人名翻译")
    
    # 获取CSV文件列表
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
        logger.warning("没有找到需要合并的CSV文件")
        return False
    
    processed_count = 0
    for csv_file in csv_files:
        # 构造文件路径
        csv_path = os.path.join(csv_dir, csv_file)
        txt_file = csv_file.replace(".csv", ".txt")
        txt_path = os.path.join(untranslated_txt_dir, txt_file)
        output_path = os.path.join(output_dir, txt_file)
        
        # 检查原始TXT文件是否存在
        if not os.path.exists(txt_path):
            logger.warning(f"跳过 {csv_file}，未找到对应的原始TXT文件")
            error_rows.append([csv_file, "N/A", "文件缺失", "", "", f"未找到对应的原始TXT文件: {txt_path}"])
            has_errors = True
            continue
        
        # 读取CSV内容
        replace_items = []
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'id' not in row or 'text' not in row or 'trans' not in row:
                        continue
                    replace_items.append((
                        row['id'], 
                        row['text'], 
                        row['trans'], 
                        row['name'] if 'name' in row else ''
                    ))
        except Exception as e:
            logger.error(f"读取CSV文件 {csv_path} 时出错: {e}")
            error_rows.append([csv_file, "N/A", "CSV读取错误", "", "", str(e)])
            has_errors = True
            continue
            
        # 按原文长度降序排序
        replace_items.sort(key=lambda x: len(x[1] or ""), reverse=True)
        
        # 读取原始文本内容
        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            logger.error(f"读取TXT文件 {txt_path} 时出错: {e}")
            error_rows.append([csv_file, "N/A", "TXT读取错误", "", "", str(e)])
            has_errors = True
            continue
        
        # 进行文本替换
        changes_count = 0
        file_has_errors = False
        
        for row_id, orig, trans, name in replace_items:
            if not orig:
                continue
                
            # 使用通用函数清理原文中的标签
            clean_orig = clean_html_tags(orig)
            
            if row_id == 'select':
                # 处理select类型 - 不需要中日双语
                pattern = re.compile(
                    r'(choice text=)(["\']?)%s\2' % re.escape(clean_orig),
                    flags=re.IGNORECASE
                )
                new_content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
                if new_content != content:
                    content = new_content
                    changes_count += 1
                    
            elif row_id == '0000000000000':
                # 处理0000000000000类型 - 需要中日双语
                try:
                    # 分割原文和翻译为行
                    parts = clean_orig.split("\\n")
                    trans_parts = trans.split("\\n")
                    
                    # 检查原文和翻译的行数是否一致
                    if len(parts) != len(trans_parts):
                        logger.warning(f"警告: 文件 {csv_file} 中ID为 {row_id} 的条目，原文和翻译的行数不一致 (原文: {len(parts)}行, 翻译: {len(trans_parts)}行)")
                        error_rows.append([
                            csv_file, row_id, "行数不匹配", 
                            clean_orig, trans, 
                            f"原文行数: {len(parts)}, 翻译行数: {len(trans_parts)}"
                        ])
                        has_errors = True
                        file_has_errors = True
                        continue  # 跳过处理此条目
                    
                    # 构建双语文本
                    bilingual_text = ""
                    for i, (part, trans_part) in enumerate(zip(parts, trans_parts)):
                        if i < len(parts) - 1:
                            bilingual_text += f"<r\\={part}>{trans_part}</r>\\r\\n"
                        else:
                            bilingual_text += f"<r\\={part}>{trans_part}</r>"
                    
                    # 替换原文
                    pattern = re.compile(
                        r'(text=)(["\']?)%s\2' % re.escape(orig),
                        flags=re.IGNORECASE
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                except Exception as e:
                    logger.error(f"处理文件 {csv_file} 中ID为 {row_id} 的条目时出错: {e}")
                    error_rows.append([csv_file, row_id, "处理错误", clean_orig, trans, str(e)])
                    has_errors = True
                    file_has_errors = True
                    
            elif row_id == 'narration':  # 处理narration - 需要中日双语
                try:
                    # 分割原文和翻译为行
                    parts = clean_orig.split("\\n")
                    trans_parts = trans.split("\\n")
                    
                    # 检查原文和翻译的行数是否一致
                    if len(parts) != len(trans_parts):
                        logger.warning(f"警告: 文件 {csv_file} 中ID为 {row_id} 的条目，原文和翻译的行数不一致 (原文: {len(parts)}行, 翻译: {len(trans_parts)}行)")
                        error_rows.append([
                            csv_file, row_id, "行数不匹配", 
                            clean_orig, trans, 
                            f"原文行数: {len(parts)}, 翻译行数: {len(trans_parts)}"
                        ])
                        has_errors = True
                        file_has_errors = True
                        continue  # 跳过处理此条目
                    
                    # 构建双语文本，使用与0000000000000类型相同的逻辑
                    bilingual_text = ""
                    for i, (part, trans_part) in enumerate(zip(parts, trans_parts)):
                        if i < len(parts) - 1:
                            bilingual_text += f"<r\\={part}>{trans_part}</r>\\r\\n"
                        else:
                            bilingual_text += f"<r\\={part}>{trans_part}</r>"
                    
                    # 替换narration标签
                    pattern = re.compile(
                        r'(narration text=)(["\']?)%s\2' % re.escape(orig),
                        flags=re.IGNORECASE
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                    
                    # 也替换可能的text属性
                    pattern = re.compile(
                        r'(text=)(["\']?)%s\2' % re.escape(orig),
                        flags=re.IGNORECASE
                    )
                    new_content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
                except Exception as e:
                    logger.error(f"处理文件 {csv_file} 中ID为 {row_id} 的条目时出错: {e}")
                    error_rows.append([csv_file, row_id, "处理错误", clean_orig, trans, str(e)])
                    has_errors = True
                    file_has_errors = True
                    
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
                    new_content = name_pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{translated_name}{m.group(2)}', content)
                    if new_content != content:
                        content = new_content
                        changes_count += 1
        
        # 如果文件处理过程中没有错误，则写入新文件
        if not file_has_errors:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"已生成中日双语文件: {output_path} (进行了 {changes_count} 处替换)")
                processed_count += 1
            except Exception as e:
                logger.error(f"写入文件 {output_path} 时出错: {e}")
                error_rows.append([csv_file, "N/A", "文件写入错误", "", "", str(e)])
                has_errors = True
        else:
            logger.warning(f"文件 {csv_file} 处理过程中存在错误，跳过生成输出文件")
    
    # 如果有错误，写入错误报告
    if has_errors:
        try:
            with open(error_report_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(error_rows)
            logger.warning(f"\n处理过程中发现错误，详细信息已保存到: {os.path.abspath(error_report_file)}")
        except Exception as e:
            logger.error(f"写入错误报告时出错: {e}")
    
    logger.info(f"\n合并完成！成功处理 {processed_count} 个文件")
    logger.info(f"翻译结果保存在: {os.path.abspath(output_dir)}")
    if has_errors:
        logger.info(f"错误报告保存在: {os.path.abspath(error_report_file)}")
    logger.info("下一步建议:")
    logger.info("1. 手动检查合并结果")
    logger.info("2. 修复错误报告中的问题")
    logger.info("3. 将最终文件复制回游戏目录")
    
    return processed_count > 0


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
