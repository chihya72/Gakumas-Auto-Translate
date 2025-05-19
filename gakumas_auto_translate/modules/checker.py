"""
检查模块，用于检查新增未翻译文件
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import shutil
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist
from gakumas_auto_translate.modules.config import get_dump_txt_path, configure_directories

# 获取日志记录器
logger = get_logger("checker")

def check_new_files():
    """对比是否有新增txt文件"""
    # 使用config模块的函数获取或配置dump_txt_path
    dump_txt_path = get_dump_txt_path()
    
    if not dump_txt_path:
        # 如果配置文件中没有有效路径，使用configure_directories函数配置
        logger.warning("未找到dump_txt目录配置，需要先设置")
        dump_txt_path = configure_directories()
        if not dump_txt_path:
            logger.error("配置dump_txt目录失败")
            return False

    # 确保data目录存在
    data_dir = get_path("data_dir")
    ensure_paths_exist(["data_dir"])
    
    try:
        # 获取两个目录的txt文件列表（仅文件名）
        data_files = set()
        dump_files = set()
        
        # 安全获取data目录文件列表
        if os.path.exists(data_dir):
            data_files = set(f for f in os.listdir(data_dir) if f.endswith(".txt"))
        else:
            logger.warning(f"data目录不存在: {data_dir}")
        
        # 安全获取dump_txt目录文件列表
        if os.path.exists(dump_txt_path):
            dump_files = set(f for f in os.listdir(dump_txt_path) if f.endswith(".txt"))
        else:
            logger.error(f"dump_txt目录不存在: {dump_txt_path}")
            return False

        # 找出新增文件
        new_files = dump_files - data_files
        if not new_files:
            logger.info("没有发现新增文件")
            return False

        logger.info(f"发现{len(new_files)}个新增文件:")
        for f in new_files:
            logger.info(f"- {f}")

        # 创建todo目录结构
        todo_dirs = [
            "todo_untranslated_txt",
            "todo_untranslated_csv_orig",
            "todo_untranslated_csv_dict",
            "todo_translated_csv",
            "todo_translated_txt"
        ]
        
        # 确保目录存在
        created_paths = ensure_paths_exist(todo_dirs)
        if created_paths:
            logger.info(f"已创建以下目录: {', '.join(created_paths)}")
        
        # 获取目标目录路径
        dest_dir = get_path("todo_untranslated_txt")

        # 复制新增文件
        copied_count = 0
        for filename in new_files:
            try:
                src = os.path.join(dump_txt_path, filename)
                dst = os.path.join(dest_dir, filename)
                shutil.copy2(src, dst)
                logger.info(f"已复制: {src} -> {dst}")
                copied_count += 1
            except FileNotFoundError:
                logger.error(f"源文件不存在: {src}")
            except PermissionError:
                logger.error(f"无权限复制文件: {src} -> {dst}")
            except Exception as e:
                logger.error(f"复制文件失败 {filename}: {e}")
        
        if copied_count > 0:
            logger.info(f"成功复制了 {copied_count} 个新增文件")
            return True
        else:
            logger.warning("没有成功复制任何文件")
            return False
            
    except Exception as e:
        logger.error(f"检查新增文件时出错: {e}")
        return False
