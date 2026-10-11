"""
检查模块，用于检查新增未翻译文件
"""

import os
import shutil
from pathlib import Path
from . import config
from .config import get_dump_txt_path, configure_directories
from .skip_list import load_untranslatable_files

def check_new_files():
    """对比是否有新增txt文件"""
    if config.get_source_mode() == 'octo':
        return download_new_files()
    # 使用config模块的函数获取或配置dump_txt_path
    dump_txt_path = get_dump_txt_path()
    
    if not dump_txt_path:
        # 如果配置文件中没有有效路径，使用configure_directories函数配置
        print("未找到dump_txt目录配置，需要先设置")
        dump_txt_path = configure_directories()

    # 确保data目录存在（虽然configure_directories已经处理过，这里为了安全保留）
    if not os.path.exists("./data"):
        os.makedirs("./data")
        print("已创建data目录")
        
    # 获取两个目录的txt文件列表（仅文件名）
    data_files = set(f for f in os.listdir("./data") if f.endswith(".txt"))
    dump_files = set(f for f in os.listdir(dump_txt_path) if f.endswith(".txt"))

    # 找出新增文件，排除预处理确认没有可翻译内容的文件。
    skipped_files = load_untranslatable_files()
    print(f"已按跳过名单排除 {len(dump_files & skipped_files)} 个剧情文本。")
    new_files = dump_files - data_files - skipped_files
    if not new_files:
        print("没有发现新增文件")
        return False

    print(f"发现{len(new_files)}个新增文件:")
    for f in new_files:
        print(f"- {f}")

    # 创建todo目录结构
    todo_dirs = [
        "./todo/untranslated/txt",
        "./todo/untranslated/csv_orig",  # 修改为csv_orig
        "./todo/untranslated/csv_dict",  # 新增csv_dict目录
        "./todo/translated/csv",
        "./todo/translated/txt"
    ]
    for d in todo_dirs:
        os.makedirs(d, exist_ok=True)
        print(f"已创建目录: {d}")

    # 复制新增文件
    dest_dir = "./todo/untranslated/txt"
    for filename in new_files:
        src = os.path.join(dump_txt_path, filename)
        dst = os.path.join(dest_dir, filename)
        shutil.copy2(src, dst)
        print(f"已复制: {src} -> {dst}")
    
    return True


def download_new_files():
    from .octo_source import OctoClient

    skipped_files = load_untranslatable_files()
    client = OctoClient(config.get_source_settings())
    manifest = client.manifest()
    config.remember_octo_version(manifest['version'])
    destination = Path('./todo/untranslated/txt')
    known = {path.name for directory in (Path('./data'), destination) for path in directory.glob('*.txt')}
    print(f"已按跳过名单排除 {sum(item['name'] in skipped_files for item in manifest['resources'])} 个剧情文本。")
    pending = [item for item in manifest['resources']
               if item['name'].startswith('adv_') and item['name'].endswith('.txt')
               and item['name'] not in skipped_files and item['name'] not in known]
    print(f"发现 {len(pending)} 个尚未收录的剧情文本。")
    if not pending:
        return False
    for directory in ('untranslated/txt', 'untranslated/csv_orig', 'untranslated/csv_dict', 'translated/csv', 'translated/txt'):
        (Path('./todo') / directory).mkdir(parents=True, exist_ok=True)
    paths, failures = client.download(pending, manifest, destination)
    print(f"已下载 {len(paths)} 个剧情到 {destination.resolve()}；可继续第 2 步。")
    if failures:
        raise RuntimeError(f"{len(failures)} 个剧情下载失败；成功文件已保留，下一次第 1 步只补缺失文件")
    return True
