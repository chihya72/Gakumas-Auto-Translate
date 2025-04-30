"""
清理模块，处理清理临时文件和最终复制功能
"""

import os
import shutil
from .utils import process_unit_files_in_folder

def cleanup_and_copy():
    """清理临时文件并复制最终文件"""
    # 第一步：处理并复制翻译文件到data目录
    source_dir = "./todo/translated/txt"
    data_dir = "./data"
    copied_files = []

    # 确保源目录存在
    if os.path.exists(source_dir):
        # 处理adv_unit_开头的文件
        print("处理adv_unit_开头的文件...")
        process_unit_files_in_folder(source_dir)
        
        # 创建目标目录（如果不存在）
        os.makedirs(data_dir, exist_ok=True)
        
        # 遍历所有txt文件
        for filename in os.listdir(source_dir):
            if filename.endswith(".txt"):
                src = os.path.join(source_dir, filename)
                dst = os.path.join(data_dir, filename)
                shutil.copy2(src, dst)
                copied_files.append(filename)
        
        if copied_files:
            print(f"已复制{len(copied_files)}个文件到data目录:")
            for f in copied_files:
                print(f"- {f}")
        else:
            print("没有需要复制的翻译文件")
    else:
        print("警告: 翻译文件目录不存在 -", source_dir)

    # 第二步：清理todo目录
    todo_dirs = [
        "./todo/untranslated/txt",
        "./todo/untranslated/csv_orig",
        "./todo/untranslated/csv_dict",
        "./todo/translated/txt"
    ]
    
    cleaned_dirs = []
    for dir_path in todo_dirs:
        if os.path.exists(dir_path):
            # 删除目录中的所有文件
            for filename in os.listdir(dir_path):
                file_path = os.path.join(dir_path, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"删除失败 {file_path}: {e}")
            cleaned_dirs.append(dir_path)
            print(f"已清空目录: {dir_path}")
    
    if not cleaned_dirs:
        print("todo目录中没有需要清理的内容")
    
    # 移动translated/csv文件到csv_data目录
    csv_source_dir = "./todo/translated/csv"
    csv_target_dir = "./csv_data"
    moved_csv_files = []
    
    if os.path.exists(csv_source_dir):
        # 确保目标目录存在
        os.makedirs(csv_target_dir, exist_ok=True)
        
        # 遍历所有csv文件并移动它们
        for filename in os.listdir(csv_source_dir):
            src = os.path.join(csv_source_dir, filename)
            dst = os.path.join(csv_target_dir, filename)
            if os.path.isfile(src):
                shutil.move(src, dst)
                moved_csv_files.append(filename)
        
        if moved_csv_files:
            print(f"已移动{len(moved_csv_files)}个CSV文件到{csv_target_dir}目录:")
            for f in moved_csv_files:
                print(f"- {f}")
        else:
            print(f"没有需要移动的CSV文件")
    else:
        print(f"警告: CSV文件目录不存在 - {csv_source_dir}")

    # 第三步：清理Gakumas的临时目录
    gakumas_tmp_dirs = [
        "./GakumasPreTranslation/tmp/untranslated",
        "./GakumasPreTranslation/tmp/translated"
    ]
    
    cleaned_gakumas = []
    for dir_path in gakumas_tmp_dirs:
        if os.path.exists(dir_path):
            # 删除目录中的所有文件
            for filename in os.listdir(dir_path):
                file_path = os.path.join(dir_path, filename)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print(f"删除失败 {file_path}: {e}")
            cleaned_gakumas.append(dir_path)
            print(f"已清空目录: {dir_path}")
    
    if not cleaned_gakumas:
        print("Gakumas临时目录中没有需要清理的内容")

    print("\n操作完成！")
    print("建议后续操作:")
    print("1. 确认data目录中的文件已更新")
    print("2. 可以将游戏切回日文模式测试翻译效果")
    
    return True