"""
Gakumas Auto Translate 主程序
用于自动翻译游戏文本的工具
"""

from .modules import config, checker, preprocessor, translator, merger, cleaner

def print_menu():
    """打印命令行菜单"""
    # 获取当前翻译模式
    mode_display = config.get_translation_mode_display()
    print(f"\n==== Gakumas Auto Translate (当前模式: {mode_display}) ====")
    print("1. 检查是否有新增未翻译文本")
    print("2. 预处理待翻译的原始文本（包含自动人名替换）")
    print("3. 翻译csv文件")
    print("4. 合并翻译文件")
    print("5. 完成并清理临时文件")
    print("6. 切换翻译模式")
    print("9. 配置并检测所需目录")
    print("0. 退出程序")

def check_config():
    """检查配置是否有效"""
    dump_txt_path = config.get_dump_txt_path()
    if not dump_txt_path:
        print("\n⚠️ 警告：未找到有效的dump_txt路径配置")
        print("请先使用功能9配置程序所需目录")
        return False
    return True

def main():
    """主程序入口"""
    # 程序启动时自动加载配置文件，但不再主动提示
    config.load_config()
    
    while True:
        print_menu()
        choice = input("请输入选项数字: ").strip()

        if choice == '1':
            # 功能1需要访问dump_txt_path，所以需要检查配置
            if not check_config():
                continue
            checker.check_new_files()
        elif choice == '2':
            # 功能2不直接访问dump_txt_path，无需检查配置
            preprocessor.preprocess_txt_files()
        elif choice == '3':
            # 功能3不直接访问dump_txt_path，无需检查配置
            translator.translate_csv_files()
        elif choice == '4':
            # 功能4不直接访问dump_txt_path，无需检查配置
            merger.merge_translations()
        elif choice == '5':
            # 功能5不直接访问dump_txt_path，无需检查配置
            cleaner.cleanup_and_copy()
        elif choice == '6':
            # 切换翻译模式
            config.toggle_translation_mode()
        elif choice == '9':
            # 配置目录并确保 config.json 已创建
            dump_txt_path = config.configure_directories()
            if dump_txt_path:
                print(f"✅ 配置成功！dump_txt路径: {dump_txt_path}")
                print("配置已保存到 config.json")
            else:
                print("❌ 配置失败，请重试")
        elif choice == '0':
            print("程序退出")
            break
        else:
            print("无效的输入，请重新选择")

if __name__ == "__main__":
    main()