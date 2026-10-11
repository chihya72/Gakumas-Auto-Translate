"""
配置模块，负责处理程序配置和目录设置
"""

import os
import json
from pathlib import Path
from .utils import create_sample_dictionary, ensure_dir_exists

# 全局配置变量
dump_txt_path = None
translation_mode = "bilingual"  # 翻译模式：bilingual（双语）或 chinese（纯中文）
source_mode = "octo"  # octo（游戏 CDN）或 local（本地解包目录）
# 配置文件路径
CONFIG_FILE = "./config.json"

def load_config():
    """从配置文件加载设置"""
    global dump_txt_path, translation_mode, source_mode
    
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                translation_mode = config.get('translation_mode', 'bilingual')
                source_mode = config.get('source_mode', 'octo')
                if source_mode == 'octo':
                    dump_txt_path = config.get('dump_txt_path')
                    return True
                if 'dump_txt_path' in config and os.path.exists(config['dump_txt_path']):
                    dump_txt_path = config['dump_txt_path']
                    # 加载翻译模式配置，默认为双语模式
                    translation_mode = config.get('translation_mode', 'bilingual')
                    return True
                else:
                    print("配置文件中的dump_txt_path不存在或无效")
                    # 即使dump_txt_path无效，也要加载翻译模式
                    translation_mode = config.get('translation_mode', 'bilingual')
                    return False
        except Exception as e:
            print(f"读取配置文件时出错: {e}")
    else:
        print(f"配置文件 {CONFIG_FILE} 不存在")
    
    return False

def save_config():
    """保存设置到配置文件"""
    global dump_txt_path, translation_mode, source_mode
    
    try:
        config = get_source_settings()
        config.update(dump_txt_path=dump_txt_path, translation_mode=translation_mode, source_mode=source_mode)
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
            return True
    except Exception as e:
        print(f"保存配置文件时出错: {e}")
        return False

def configure_directories():
    """配置并检测所需目录"""
    global dump_txt_path, source_mode

    choice = input(f"资源来源：1. Octo/CDN（当前：{source_mode}） 2. 本地解包目录；回车保留：").strip()
    if choice not in {'', '1', '2'}:
        print("无效的来源选项")
        return None
    if choice:
        source_mode = 'octo' if choice == '1' else 'local'
    if source_mode == 'octo':
        save_config()
        print("第 1 步将直接下载新增剧情到 todo\\untranslated\\txt。")
        return './todo/untranslated/txt'
    
    # 检查/创建data目录
    data_dir = "./data"
    if ensure_dir_exists(data_dir):
        print(f"已创建目录: {data_dir}")
    else:
        print(f"目录已存在: {data_dir}")

    # 配置dump_txt目录
    while True:
        path = input("请输入dump_txt目录路径（留空使用默认./dump_txt）: ").strip()
        temp_path = path if path else "./dump_txt"
        
        if not os.path.exists(temp_path):
            choice = input("目录不存在，是否创建？(y/n): ").lower()
            if choice == 'y':
                os.makedirs(temp_path)
                print(f"已创建目录: {temp_path}")
                dump_txt_path = temp_path
                # 保存配置到文件
                save_config()
                break
            else:
                continue
        else:
            print(f"目录已存在: {temp_path}")
            dump_txt_path = temp_path
            # 保存配置到文件
            save_config()
            break
    
    # 检查字典文件
    dict_file = "./name_dictionary.json"
    if not os.path.exists(dict_file):
        # 如果不存在，创建一个示例字典文件
        create_sample_dictionary(dict_file)
        print(f"已创建示例字典文件: {dict_file}")
        print("请编辑此文件添加需要替换的人名和称谓")
    
    return dump_txt_path

def get_dump_txt_path():
    """获取dump_txt路径，只从配置文件中读取"""
    global dump_txt_path
    
    # 如果当前没有加载配置，尝试加载
    if dump_txt_path is None:
        load_config()
        
    return dump_txt_path

def get_source_mode():
    return source_mode


def get_source_settings():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, encoding='utf-8-sig') as file:
            return json.load(file)
    return {}


def remember_octo_version(version):
    settings = get_source_settings()
    settings['octo_version'] = version
    with open(CONFIG_FILE, 'w', encoding='utf-8') as file:
        json.dump(settings, file, ensure_ascii=False, indent=4)


def set_dump_txt_path(path):
    """设置dump_txt路径"""
    global dump_txt_path
    if os.path.exists(path):
        dump_txt_path = path
        # 当路径变更时，保存到配置文件
        save_config()
        return True
    else:
        print(f"路径不存在: {path}")
        return False

def get_translation_mode():
    """获取当前翻译模式"""
    global translation_mode
    
    # 如果当前没有加载配置，尝试加载
    if translation_mode is None:
        load_config()
        
    return translation_mode

def set_translation_mode(mode):
    """设置翻译模式"""
    global translation_mode
    
    if mode in ['bilingual', 'chinese']:
        translation_mode = mode
        # 保存配置到文件
        save_config()
        return True
    else:
        print(f"无效的翻译模式: {mode}")
        return False

def get_translation_mode_display():
    """获取翻译模式的显示名称"""
    mode = get_translation_mode()
    return "中日双语" if mode == "bilingual" else "纯中文"

def toggle_translation_mode():
    """切换翻译模式"""
    current_mode = get_translation_mode()
    new_mode = "chinese" if current_mode == "bilingual" else "bilingual"
    if set_translation_mode(new_mode):
        print(f"翻译模式已切换为: {get_translation_mode_display()}")
        return True
    return False
