import os
import shutil
import re
import csv
import subprocess
from pathlib import Path

dump_txt_path = None  # 存储dump_txt路径的全局变量

def print_menu():
    """打印命令行菜单"""
    print("\n==== 主菜单 ====")
    print("1. 检查是否有新增未翻译文本")
    print("2. 预处理待翻译的原始文本为csv文件")
    print("3. 翻译csv文件")
    print("4. 合并翻译文件")
    print("5. 完成并清理临时文件")  # 新增的选项5
    print("9. 配置并检测所需目录")
    print("0. 退出程序")

def configure_directories():
    """配置并检测所需目录"""
    global dump_txt_path
    
    # 检查/创建data目录
    data_dir = "./data"
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"已创建目录: {data_dir}")
    else:
        print(f"目录已存在: {data_dir}")

    # 检查dump_txt目录
    while True:
        if dump_txt_path and os.path.exists(dump_txt_path):
            print(f"当前dump_txt目录: {dump_txt_path}")
            break
            
        path = input("请输入dump_txt目录路径（留空使用默认./dump_txt）: ").strip()
        dump_txt_path = path if path else "./dump_txt"
        
        if not os.path.exists(dump_txt_path):
            choice = input("目录不存在，是否创建？(y/n): ").lower()
            if choice == 'y':
                os.makedirs(dump_txt_path)
                print(f"已创建目录: {dump_txt_path}")
                break
            else:
                dump_txt_path = None
        else:
            print(f"目录已存在: {dump_txt_path}")
            break

def check_new_files():
    """对比是否有新增txt文件"""
    if not dump_txt_path:
        print("请先配置dump_txt目录（选项9）")
        return

    # 获取两个目录的txt文件列表（仅文件名）
    data_files = set(f for f in os.listdir("./data") if f.endswith(".txt"))
    dump_files = set(f for f in os.listdir(dump_txt_path) if f.endswith(".txt"))

    # 找出新增文件
    new_files = dump_files - data_files
    if not new_files:
        print("没有发现新增文件")
        return

    print(f"发现{len(new_files)}个新增文件:")
    for f in new_files:
        print(f"- {f}")

    # 创建todo目录结构
    todo_dirs = [
        "./todo/untranslated/txt",
        "./todo/untranslated/csv",
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

def preprocess_txt_files():
    """预处理待翻译的txt文件"""
    # 定义路径常量
    source_dir = "./todo/untranslated/txt"
    output_dir = "./todo/untranslated/csv"
    
    # 创建输出目录（如果不存在）
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    # 处理所有txt文件
    for filename in os.listdir(source_dir):
        if not filename.endswith(".txt"):
            continue
            
        input_path = os.path.join(source_dir, filename)
        output_path = os.path.join(output_dir, filename.replace(".txt", ".csv"))
        
        # 存储提取的内容
        extracted_data = []
        
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                
                # 匹配message类型
                message_match = re.match(r'\[message text=(.*?)\s*name=([^\s]+)', line)
                if message_match:
                    text_content = message_match.group(1).strip('"')
                    name_content = message_match.group(2).split()[0].strip('"')
                    extracted_data.append({
                        'id': '0000000000000',
                        'name': name_content,
                        'text': text_content,
                        'trans': ''
                    })
                    continue
                
                # 匹配choices类型
                choices_match = re.findall(r'choice text=([^]]+?)\]', line)
                if choices_match:
                    for choice_text in choices_match:
                        clean_text = choice_text.strip('"')
                        extracted_data.append({
                            'id': 'select',
                            'name': '',
                            'text': clean_text,
                            'trans': ''
                        })
        
        # 记录添加info行前的数据量
        original_length = len(extracted_data)
        # 添加info行到列表末尾
        extracted_data.append({
            'id': 'info',
            'name': filename,
            'text': '',
            'trans': ''
        })
        
        # 仅当存在有效数据时才生成CSV文件
        if original_length > 0:
            # 写入CSV文件
            with open(output_path, 'w', encoding='utf-8', newline='') as csvfile:
                fieldnames = ['id', 'name', 'text', 'trans']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for row in extracted_data:
                    writer.writerow(row)
                    
            print(f"已生成预处理文件: {output_path}")
        else:
            print(f"跳过文件 {filename}，未找到可翻译内容")

def translate_csv_files():
    """处理CSV文件翻译流程"""
    gakumas_dir = "./GakumasPreTranslation"
    
    # 检查Gakumas项目目录是否存在
    if not os.path.exists(gakumas_dir):
        print("未找到GakumasPreTranslation目录，请执行以下操作：")
        print("git clone https://github.com/imas-tools/GakumasPreTranslation.git")
        print("或手动克隆项目到当前目录")
        return

    # 检查.env文件是否存在
    env_path = os.path.join(gakumas_dir, ".env")
    if not os.path.exists(env_path):
        sample_env = os.path.join(gakumas_dir, ".env.sample")
        if os.path.exists(sample_env):
            shutil.copy(sample_env, env_path)
            print("已创建.env文件，请修改以下内容：")
            print("1. 配置翻译API密钥（如DEEPL_AUTH_KEY）")
            print("2. 设置翻译引擎参数")
            print("文件路径:", os.path.abspath(env_path))
        else:
            print("错误：缺失.env.sample文件，请检查GakumasPreTranslation项目完整性")
            return

    # 检查临时目录状态
    tmp_dirs = [
        os.path.join(gakumas_dir, "tmp", "untranslated"),
        os.path.join(gakumas_dir, "tmp", "translated")
    ]
    
    # 检查目录是否为空
    dirs_not_empty = []
    for d in tmp_dirs:
        if os.path.exists(d) and len(os.listdir(d)) > 0:
            dirs_not_empty.append(d)
    
    if dirs_not_empty:
        print("以下目录需要清空才能继续操作：")
        for d in dirs_not_empty:
            print("-", os.path.abspath(d))
        print("请确认是否需要执行选项4，或手动清理目录内容后重试")
        return

    # 准备复制CSV文件
    source_dir = "./todo/untranslated/csv"
    target_dir = tmp_dirs[0]  # untranslated目录
    
    # 创建目标目录（如果不存在）
    os.makedirs(target_dir, exist_ok=True)
    
    # 获取待复制文件列表
    csv_files = [f for f in os.listdir(source_dir) if f.endswith(".csv")]
    if not csv_files:
        print("没有需要翻译的CSV文件")
        print("请先执行选项2生成预处理文件")
        return

    # 执行文件复制
    print("正在复制翻译文件...")
    for filename in csv_files:
        src = os.path.join(source_dir, filename)
        dst = os.path.join(target_dir, filename)
        shutil.copy2(src, dst)
        print(f"已复制: {filename}")

    # 输出后续指引
    print("\n请手动执行以下操作：")
    print("1. 进入GakumasPreTranslation目录,在目录下执行yarn命令安装依赖")
    print("2. 根据项目文档配置翻译参数")
    print("3. 在/tmp/untranslated运行翻译脚本'yarn translate:folder'")
    print("4. 完成翻译后返回本程序执行选项4（合并翻译文件）")
    print("翻译输入目录:", os.path.abspath(target_dir))
    print("翻译输出目录:", os.path.abspath(tmp_dirs[1]))

def merge_translations():
    """合并翻译文件的主函数"""
    # 步骤1: 检查目录文件一致性
    gakumas_translated_dir = "./GakumasPreTranslation/tmp/translated"
    gakumas_untranslated_dir = "./GakumasPreTranslation/tmp/untranslated"
    
    # 检查目录是否存在
    if not os.path.exists(gakumas_translated_dir) or not os.path.exists(gakumas_untranslated_dir):
        print("错误：Gakumas翻译目录不存在，请先完成翻译流程")
        return
    
    # 获取两个目录的CSV文件列表
    translated_files = set(f for f in os.listdir(gakumas_translated_dir) if f.endswith(".csv"))
    untranslated_files = set(f for f in os.listdir(gakumas_untranslated_dir) if f.endswith(".csv"))
    
    # 比较文件集合
    if translated_files != untranslated_files:
        print("错误：翻译目录文件不一致")
        print(f"未翻译目录文件: {untranslated_files - translated_files}")
        print(f"多余翻译文件: {translated_files - untranslated_files}")
        return
    
    # 步骤2: 复制CSV文件
    target_csv_dir = "./todo/translated/csv"
    os.makedirs(target_csv_dir, exist_ok=True)
    
    print("正在复制翻译后的CSV文件...")
    for filename in translated_files:
        src = os.path.join(gakumas_translated_dir, filename)
        dst = os.path.join(target_csv_dir, filename)
        shutil.copy2(src, dst)
        print(f"已复制: {filename}")
    
    # 步骤3: 用户选择合并模式
    while True:
        print("\n请选择合并模式:")
        print("1. 纯中文（仅保留翻译内容）")
        print("2. 中日双语（保留原文和翻译）")
        choice = input("请输入选项(1/2): ").strip()
        
        if choice == '1':
            process_pure_chinese()
            break
        elif choice == '2':
            process_bilingual()
            break
        else:
            print("无效输入，请重新选择")

def process_pure_chinese():
    """处理纯中文合并逻辑"""
    # 定义路径常量
    csv_dir = "./todo/translated/csv"
    untranslated_txt_dir = "./todo/untranslated/txt"
    output_dir = "./todo/translated/txt"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取CSV文件列表
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    
    for csv_file in csv_files:
        # 构造文件路径
        csv_path = os.path.join(csv_dir, csv_file)
        txt_file = csv_file.replace(".csv", ".txt")
        txt_path = os.path.join(untranslated_txt_dir, txt_file)
        output_path = os.path.join(output_dir, txt_file)
        
        # 检查原始TXT文件是否存在
        if not os.path.exists(txt_path):
            print(f"警告：跳过 {csv_file}，未找到对应的原始TXT文件")
            continue
        
        # 读取CSV内容
        rows = []
        orig_texts = []
        trans_texts = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row['id'])
                orig_texts.append(row['text'])
                trans_texts.append(row['trans'])
        
        # 读取原始文本内容
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 进行文本替换
        for row_id, orig, trans in zip(rows, orig_texts, trans_texts):
            if not orig:
                continue
        
            # 转义特殊字符
            escaped_orig = re.escape(orig)
        
            if row_id == 'select':
                # 处理choice类型
                pattern = re.compile(
                    r'(choice text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
    
            elif row_id == '0000000000000':
                # 处理message类型
                pattern = re.compile(
                    r'(text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
        
        # 写入新文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已生成纯中文文件: {output_path}")

    print("\n合并完成！请检查以下目录:")
    print(f"- 翻译结果: {os.path.abspath(output_dir)}")
    print("下一步建议:")
    print("1. 手动检查合并结果")
    print("2. 将最终文件复制回游戏目录")


def process_bilingual():
    """处理中日双语合并逻辑"""
    # 定义路径常量
    csv_dir = "./todo/translated/csv"
    untranslated_txt_dir = "./todo/untranslated/txt"
    output_dir = "./todo/translated/txt"
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取CSV文件列表
    csv_files = [f for f in os.listdir(csv_dir) if f.endswith(".csv")]
    
    for csv_file in csv_files:
        # 构造文件路径
        csv_path = os.path.join(csv_dir, csv_file)
        txt_file = csv_file.replace(".csv", ".txt")
        txt_path = os.path.join(untranslated_txt_dir, txt_file)
        output_path = os.path.join(output_dir, txt_file)
        
        # 检查原始TXT文件是否存在
        if not os.path.exists(txt_path):
            print(f"警告：跳过 {csv_file}，未找到对应的原始TXT文件")
            continue
        
        # 读取CSV内容
        rows = []
        orig_texts = []
        trans_texts = []
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row['id'])
                orig_texts.append(row['text'])
                trans_texts.append(row['trans'])
        
        # 读取原始文本内容
        with open(txt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 进行文本替换
        for row_id, orig, trans in zip(rows, orig_texts, trans_texts):
            if not orig:
                continue
        
            # 转义特殊字符
            escaped_orig = re.escape(orig)
        
            if row_id == 'select':
                # 处理choice类型
                pattern = re.compile(
                    r'(choice text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{trans}{m.group(2)}', content)
    
            elif row_id == '0000000000000':
                # 处理message类型
                # 分割文本为多个部分（按 \n 分割）
                parts = orig.split("\\n")
                trans_parts = trans.split("\\n")
                
                # 生成中日双语格式：每行对应一对
                bilingual_text = ""
                for i, (part, trans_part) in enumerate(zip(parts, trans_parts)):
                    if i < len(parts) - 1:  # 如果不是最后一行，添加 \r\n
                        bilingual_text += f"<r\\={part}>{trans_part}</r>\\r\\n"
                    else:  # 最后一行不添加 \r\n
                        bilingual_text += f"<r\\={part}>{trans_part}</r>"
                
                # 替换原始内容中的 text 部分
                pattern = re.compile(
                    r'(text=)(["\']?)%s\2' % re.escape(orig),
                    flags=re.IGNORECASE
                )
                content = pattern.sub(lambda m: f'{m.group(1)}{m.group(2)}{bilingual_text}{m.group(2)}', content)
        
        # 写入新文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"已生成中日双语文件: {output_path}")

    print("\n合并完成！请检查以下目录:")
    print(f"- 翻译结果: {os.path.abspath(output_dir)}")
    print("下一步建议:")
    print("1. 手动检查合并结果")
    print("2. 将最终文件复制回游戏目录")

    
    
    
def cleanup_and_copy():
    """清理临时文件并复制最终文件"""
    # 第一步：复制翻译文件到data目录
    source_dir = "./todo/translated/txt"
    data_dir = "./data"
    copied_files = []

    # 确保源目录存在
    if os.path.exists(source_dir):
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
        "./todo/untranslated/csv",
        "./todo/translated/csv",
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

def main():
    while True:
        print_menu()
        choice = input("请输入选项数字: ").strip()

        if choice == '9':
            configure_directories()
        elif choice == '0':
            print("程序退出")
            break
        elif choice == '1':
            check_new_files()
        elif choice == '2':
            preprocess_txt_files()
        elif choice == '3':
            translate_csv_files()
        elif choice == '4':
            merge_translations()
        elif choice == '5':  # 新增选项5的处理
            cleanup_and_copy()
        else:
            print("无效的输入，请重新选择")

if __name__ == "__main__":
    main()