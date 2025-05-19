"""
主模块，提供用户界面和功能入口
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import sys
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist
from gakumas_auto_translate.modules.utils import validate_input

# 导入功能模块
from gakumas_auto_translate.modules.config import load_config, configure_directories
from gakumas_auto_translate.modules.checker import check_new_files
from gakumas_auto_translate.modules.preprocessor import preprocess_txt_files
from gakumas_auto_translate.modules.translator import translate_csv_files
from gakumas_auto_translate.modules.merger import process_bilingual
from gakumas_auto_translate.modules.cleaner import cleanup_and_copy

# 获取日志记录器
logger = get_logger("main")

def show_menu():
    """显示主菜单"""
    print("\n===== Gakumas Auto Translate =====")
    print("1. 检查新增文件")
    print("2. 预处理文件")
    print("3. 准备翻译")
    print("4. 合并翻译文件")
    print("5. 清理并复制")
    print("0. 退出")
    print("=================================")

def check_config():
    """检查配置是否有效"""
    if not load_config():
        print("需要先配置dump_txt目录")
        configure_directories()
    return True

def main():
    """主函数"""
    # 确保基本目录结构存在
    ensure_paths_exist(["data_dir", "csv_data_dir"])
    
    # 加载配置
    load_config()
    
    while True:
        try:
            show_menu()
            choice = input("请输入选项数字: ").strip()
            
            # 验证输入
            valid, value = validate_input(choice, 'number', 0, 5)
            if not valid:
                logger.warning(value)  # value 包含错误信息
                continue
            
            choice = value  # 使用验证后的数值
            
            if choice == 0:
                logger.info("程序已退出")
                break
                
            elif choice == 1:
                # 功能1: 检查新增文件
                # 需要先检查配置
                if not check_config():
                    continue
                check_new_files()
                
            elif choice == 2:
                # 功能2: 预处理文件
                preprocess_txt_files()
                
            elif choice == 3:
                # 功能3: 准备翻译
                translate_csv_files()
                
            elif choice == 4:
                # 功能4: 合并翻译文件
                process_bilingual()
                
            elif choice == 5:
                # 功能5: 清理并复制
                cleanup_and_copy()
            
            input("\n按Enter键继续...")
            
        except KeyboardInterrupt:
            logger.info("\n程序已被用户中断")
            break
        except Exception as e:
            logger.error(f"发生错误: {e}")
            input("\n按Enter键继续...")

if __name__ == "__main__":
    main()
