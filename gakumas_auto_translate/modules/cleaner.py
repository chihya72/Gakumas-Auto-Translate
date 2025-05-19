"""
清理模块，处理清理临时文件和最终复制功能
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import shutil
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist
from gakumas_auto_translate.modules.utils import process_unit_files_in_folder

# 获取日志记录器
logger = get_logger("cleaner")

def cleanup_and_copy():
    """清理临时文件并复制最终文件"""
    # 获取路径
    source_dir = get_path("todo_translated_txt")
    data_dir = get_path("data_dir")
    csv_source_dir = get_path("todo_translated_csv")
    csv_target_dir = get_path("csv_data_dir")
    
    # 确保目标目录存在
    ensure_paths_exist(["data_dir", "csv_data_dir"])
    
    # 第一步：处理并复制翻译文件到data目录
    copied_files = []

    # 确保源目录存在
    if os.path.exists(source_dir):
        try:
            # 处理adv_unit_开头的文件
            logger.info("处理adv_unit_开头的文件...")
            process_unit_files_in_folder(source_dir)
            
            # 遍历所有txt文件
            for filename in os.listdir(source_dir):
                if filename.endswith(".txt"):
                    try:
                        src = os.path.join(source_dir, filename)
                        dst = os.path.join(data_dir, filename)
                        shutil.copy2(src, dst)
                        copied_files.append(filename)
                    except FileNotFoundError:
                        logger.error(f"源文件不存在: {src}")
                    except PermissionError:
                        logger.error(f"无权限复制文件: {src} -> {dst}")
                    except Exception as e:
                        logger.error(f"复制文件失败 {filename}: {e}")
            
            if copied_files:
                logger.info(f"已复制{len(copied_files)}个文件到data目录:")
                for f in copied_files:
                    logger.info(f"- {f}")
            else:
                logger.warning("没有需要复制的翻译文件")
        except Exception as e:
            logger.error(f"处理翻译文件时出错: {e}")
    else:
        logger.warning(f"翻译文件目录不存在: {source_dir}")

    # 第二步：清理todo目录
    todo_dirs = [
        "todo_untranslated_txt",
        "todo_untranslated_csv_orig",
        "todo_untranslated_csv_dict",
        "todo_translated_txt"
    ]
    
    cleaned_dirs = []
    for dir_key in todo_dirs:
        dir_path = get_path(dir_key)
        if os.path.exists(dir_path):
            try:
                # 删除目录中的所有文件
                for filename in os.listdir(dir_path):
                    file_path = os.path.join(dir_path, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        logger.error(f"删除失败 {file_path}: {e}")
                cleaned_dirs.append(dir_path)
                logger.info(f"已清空目录: {dir_path}")
            except Exception as e:
                logger.error(f"清理目录失败 {dir_path}: {e}")
    
    if not cleaned_dirs:
        logger.info("todo目录中没有需要清理的内容")
    
    # 移动translated/csv文件到csv_data目录
    moved_csv_files = []
    
    if os.path.exists(csv_source_dir):
        try:
            # 确保目标目录存在
            os.makedirs(csv_target_dir, exist_ok=True)
            
            # 遍历所有csv文件并移动它们
            for filename in os.listdir(csv_source_dir):
                try:
                    src = os.path.join(csv_source_dir, filename)
                    dst = os.path.join(csv_target_dir, filename)
                    if os.path.isfile(src):
                        # 使用临时文件进行原子移动
                        temp_dst = dst + ".tmp"
                        shutil.copy2(src, temp_dst)
                        os.replace(temp_dst, dst)
                        os.unlink(src)
                        moved_csv_files.append(filename)
                except FileNotFoundError:
                    logger.error(f"源文件不存在: {src}")
                except PermissionError:
                    logger.error(f"无权限移动文件: {src} -> {dst}")
                except Exception as e:
                    logger.error(f"移动文件失败 {filename}: {e}")
            
            if moved_csv_files:
                logger.info(f"已移动{len(moved_csv_files)}个CSV文件到{csv_target_dir}目录:")
                for f in moved_csv_files:
                    logger.info(f"- {f}")
            else:
                logger.info(f"没有需要移动的CSV文件")
        except Exception as e:
            logger.error(f"移动CSV文件时出错: {e}")
    else:
        logger.warning(f"CSV文件目录不存在: {csv_source_dir}")

    # 第三步：清理Gakumas的临时目录
    gakumas_tmp_dirs = [
        "gakumas_tmp_untranslated",
        "gakumas_tmp_translated"
    ]
    
    cleaned_gakumas = []
    for dir_key in gakumas_tmp_dirs:
        dir_path = get_path(dir_key)
        if os.path.exists(dir_path):
            try:
                # 删除目录中的所有文件
                for filename in os.listdir(dir_path):
                    file_path = os.path.join(dir_path, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                        elif os.path.isdir(file_path):
                            shutil.rmtree(file_path)
                    except Exception as e:
                        logger.error(f"删除失败 {file_path}: {e}")
                cleaned_gakumas.append(dir_path)
                logger.info(f"已清空目录: {dir_path}")
            except Exception as e:
                logger.error(f"清理目录失败 {dir_path}: {e}")
    
    if not cleaned_gakumas:
        logger.info("Gakumas临时目录中没有需要清理的内容")

    logger.info("\n操作完成！")
    logger.info("建议后续操作:")
    logger.info("1. 确认data目录中的文件已更新")
    logger.info("2. 可以将游戏切回日文模式测试翻译效果")
    
    # 返回操作结果
    success = len(copied_files) > 0 or len(moved_csv_files) > 0
    return success
