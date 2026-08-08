"""
工具模块，包含共享的实用函数
"""

import csv
import os
import re
import json
import shutil
from pathlib import Path

import pandas as pd

# ---------- 同组段落合并（cidol / csprt） ----------
# cidol-<角色>-3-<话> 的 01~03、csprt-<批次>-<卡号> 的 01~03 是一张卡的一个完整
# 故事。分成三次请求时后段看不到前段，剧情就断了；拼成一个 CSV 一次翻完，模型
# 才能看到完整的起承转合。本地菜单和自动管线共用这两个函数，避免两套行为。
GROUP_MERGE_RE = re.compile(r"^adv_(cidol|csprt)-.*_\d+$")
# CSV 末尾的元数据行（非台词）
META_IDS = ("info", "译者")
# 合并台账文件名：菜单3 写、菜单4 读（两次独立调用之间要持久化）
GROUP_MANIFEST = "group_manifest.json"


def merge_groups(files, dst):
    """把同组段落拼成一个 CSV 写进 dst，返回 {合并后文件名: [(原文件名, 台词行数), ...]}。

    不同组的文件原样复制。返回的台账供 split_merged 按行数拆回。
    """
    dst = Path(dst)
    groups = {}
    for f in sorted(Path(p) for p in files):
        story, _, _ = f.stem.rpartition("_")
        key = story if story and GROUP_MERGE_RE.match(f.stem) else f.stem
        groups.setdefault(key, []).append(f)

    manifest = {}
    for parts in groups.values():
        if len(parts) == 1:
            shutil.copy2(parts[0], dst / parts[0].name)
            continue
        merged_rows, fieldnames, layout, first_info = [], None, [], None
        for f in parts:
            with f.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
                fieldnames = fieldnames or reader.fieldnames
            # info/译者 每段各有一份。全带上的话翻译引擎会取到【最后】一个 info
            # 当输出文件名，结果就写成了最后一段的名字。只留第一段的 info。
            data = [r for r in rows if r.get("id") not in META_IDS]
            if first_info is None:
                first_info = next((r for r in rows if r.get("id") == "info"), None)
            merged_rows.extend(data)
            layout.append((f.name, len(data)))
        if first_info is not None:
            merged_rows.append(first_info)
        name = parts[0].name
        with (dst / name).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(merged_rows)
        manifest[name] = layout
        print(f"合并同组: {name} <- {', '.join(n for n, _ in layout)}")
    return manifest


def split_merged(translated_path, layout, out_dir):
    """把合并翻译的结果按行数拆回各段，返回拆出的文件路径列表。

    合并时每段只留台词行、info 只保留第一段那份；引擎输出时又补上自己的
    info + 译者。所以先剥掉全部元数据行，按 layout 切开，再给每段补回
    【它自己的】info 和共用的译者行。
    """
    translated_path, out_dir = Path(translated_path), Path(out_dir)
    with translated_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    translator = next((r for r in rows if r.get("id") == "译者"), None)
    data = [r for r in rows if r.get("id") not in META_IDS]
    expected = sum(n for _, n in layout)
    if len(data) != expected:
        print(f"!! 合并结果行数不符（{len(data)} != {expected}），跳过: {translated_path.name}")
        return []
    out, cursor = [], 0
    for name, count in layout:
        part = data[cursor:cursor + count]
        cursor += count
        part = part + [{"id": "info", "name": name[:-len(".csv")] + ".txt",
                        "text": "", "trans": ""}]
        if translator:
            part = part + [translator]
        dest = out_dir / name
        with dest.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(part)
        out.append(dest)
    return out

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
    text = re.sub(r'<r\\=[^>]+>([\s\S]*?)(?:</r>|/r>)', r'\1', text)
    # 再处理 <em\=...>内容</em>
    text = re.sub(r'<em\\=[^>]*>([\s\S]*?)</em>', r'\1', text)
    # 处理 <em>内容</em>
    text = re.sub(r'<em>([\s\S]*?)</em>', r'\1', text)
    text = re.sub(r'<([A-Za-z][A-Za-z0-9_:-]*)(?:\\=[^>]*)?>([\s\S]*?)</\1>', r'\2', text)
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
