"""
路径管理模块，集中管理项目中使用的所有路径
"""

import os
import sys

# 获取基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 配置文件路径
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# 字典文件路径
DICT_FILE = os.path.join(BASE_DIR, "name_dictionary.json")

# 项目目录结构
def get_project_paths():
    """获取项目中使用的所有路径"""
    paths = {
        "base_dir": BASE_DIR,
        "config_file": CONFIG_FILE,
        "dict_file": DICT_FILE,
        "data_dir": os.path.join(BASE_DIR, "data"),
        "csv_data_dir": os.path.join(BASE_DIR, "csv_data"),
        "todo_dir": os.path.join(BASE_DIR, "todo"),
        "todo_untranslated_txt": os.path.join(BASE_DIR, "todo", "untranslated", "txt"),
        "todo_untranslated_csv_orig": os.path.join(BASE_DIR, "todo", "untranslated", "csv_orig"),
        "todo_untranslated_csv_dict": os.path.join(BASE_DIR, "todo", "untranslated", "csv_dict"),
        "todo_translated_csv": os.path.join(BASE_DIR, "todo", "translated", "csv"),
        "todo_translated_txt": os.path.join(BASE_DIR, "todo", "translated", "txt"),
        "gakumas_dir": os.path.join(BASE_DIR, "GakumasPreTranslation"),
        "gakumas_tmp_untranslated": os.path.join(BASE_DIR, "GakumasPreTranslation", "tmp", "untranslated"),
        "gakumas_tmp_translated": os.path.join(BASE_DIR, "GakumasPreTranslation", "tmp", "translated"),
    }
    return paths

def ensure_paths_exist(paths_to_check=None):
    """确保指定的路径存在，如不存在则创建"""
    all_paths = get_project_paths()
    
    # 如果没有指定路径，则检查所有路径
    if paths_to_check is None:
        paths_to_check = all_paths.keys()
    
    created_paths = []
    for key in paths_to_check:
        if key in all_paths:
            path = all_paths[key]
            # 跳过文件路径，只处理目录路径
            if key.endswith('_file') or key.endswith('_dir') == False:
                continue
            
            if not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                    created_paths.append(path)
                except Exception as e:
                    print(f"创建目录失败 {path}: {e}")
    
    return created_paths

def get_path(path_key):
    """获取指定的路径"""
    paths = get_project_paths()
    return paths.get(path_key, None)

def normalize_path(path):
    """标准化路径，处理不同操作系统的路径分隔符"""
    return os.path.normpath(path)
