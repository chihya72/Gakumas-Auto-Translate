
import os
import csv
from collections import Counter
import glob

def analyze_translators(csv_folder_path):
    """
    分析CSV文件夹中所有文件的译者信息
    
    Args:
        csv_folder_path (str): CSV文件夹路径
    
    Returns:
        dict: 包含统计结果的字典
    """
    translator_count = Counter()
    file_translator_mapping = {}
    files_without_translator = []
    
    # 获取所有CSV文件
    csv_files = glob.glob(os.path.join(csv_folder_path, "*.csv"))
    
    print(f"找到 {len(csv_files)} 个CSV文件")
    
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                lines = file.readlines()
                
                # 检查最后一行是否包含译者信息
                if lines:
                    last_line = lines[-1].strip()
                    
                    # 解析最后一行
                    if last_line.startswith('译者,'):
                        # 使用CSV解析器来正确处理可能包含逗号的字段
                        csv_reader = csv.reader([last_line])
                        row = next(csv_reader)
                        
                        if len(row) >= 2:
                            translator = row[1].strip()
                            if translator:  # 如果译者字段不为空
                                translator_count[translator] += 1
                                file_translator_mapping[os.path.basename(csv_file)] = translator
                            else:
                                files_without_translator.append(os.path.basename(csv_file))
                        else:
                            files_without_translator.append(os.path.basename(csv_file))
                    else:
                        files_without_translator.append(os.path.basename(csv_file))
                else:
                    files_without_translator.append(os.path.basename(csv_file))
                    
        except Exception as e:
            print(f"处理文件 {csv_file} 时出错: {e}")
            files_without_translator.append(os.path.basename(csv_file))
    
    return {
        'translator_count': translator_count,
        'file_translator_mapping': file_translator_mapping,
        'files_without_translator': files_without_translator
    }

def print_results(results):
    """
    打印分析结果
    
    Args:
        results (dict): analyze_translators函数返回的结果
    """
    translator_count = results['translator_count']
    file_translator_mapping = results['file_translator_mapping']
    files_without_translator = results['files_without_translator']
    
    print("\n" + "="*50)
    print("译者统计结果")
    print("="*50)
    
    print(f"\n总共处理了 {len(file_translator_mapping) + len(files_without_translator)} 个文件")
    print(f"有译者信息的文件: {len(file_translator_mapping)} 个")
    print(f"无译者信息的文件: {len(files_without_translator)} 个")
    
    print("\n译者统计 (按文件数量排序):")
    print("-" * 30)
    for translator, count in translator_count.most_common():
        print(f"{translator}: {count} 个文件")
    
    if files_without_translator:
        print(f"\n无译者信息的文件 (共{len(files_without_translator)}个):")
        print("-" * 30)
        for i, filename in enumerate(files_without_translator[:10], 1):  # 只显示前10个
            print(f"{i}. {filename}")
        if len(files_without_translator) > 10:
            print(f"... 还有 {len(files_without_translator) - 10} 个文件")
    
    print("\n详细的文件-译者映射 (前20个文件):")
    print("-" * 30)
    for i, (filename, translator) in enumerate(list(file_translator_mapping.items())[:20], 1):
        print(f"{i}. {filename} -> {translator}")
    
    if len(file_translator_mapping) > 20:
        print(f"... 还有 {len(file_translator_mapping) - 20} 个文件")

def save_results_to_file(results, output_file="translator_analysis.txt"):
    """
    将结果保存到文件
    
    Args:
        results (dict): analyze_translators函数返回的结果
        output_file (str): 输出文件名
    """
    translator_count = results['translator_count']
    file_translator_mapping = results['file_translator_mapping']
    files_without_translator = results['files_without_translator']
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("CSV文件译者统计分析报告\n")
        f.write("="*50 + "\n\n")
        
        f.write(f"总共处理了 {len(file_translator_mapping) + len(files_without_translator)} 个文件\n")
        f.write(f"有译者信息的文件: {len(file_translator_mapping)} 个\n")
        f.write(f"无译者信息的文件: {len(files_without_translator)} 个\n\n")
        
        f.write("译者统计 (按文件数量排序):\n")
        f.write("-" * 30 + "\n")
        for translator, count in translator_count.most_common():
            f.write(f"{translator}: {count} 个文件\n")
        
        f.write("\n详细的文件-译者映射:\n")
        f.write("-" * 30 + "\n")
        for filename, translator in sorted(file_translator_mapping.items()):
            f.write(f"{filename} -> {translator}\n")
        
        if files_without_translator:
            f.write(f"\n无译者信息的文件:\n")
            f.write("-" * 30 + "\n")
            for filename in sorted(files_without_translator):
                f.write(f"{filename}\n")
    
    print(f"\n结果已保存到文件: {output_file}")

def main():
    # CSV文件夹路径
    csv_folder_path = r"d:\GIT\Gakumas-Auto-Translate\csv_data"
    
    # 检查文件夹是否存在
    if not os.path.exists(csv_folder_path):
        print(f"错误: 文件夹 {csv_folder_path} 不存在")
        return
    
    print(f"开始分析文件夹: {csv_folder_path}")
    
    # 分析译者信息
    results = analyze_translators(csv_folder_path)
    
    # 打印结果
    print_results(results)
    
    # 保存结果到文件
    save_results_to_file(results)

if __name__ == "__main__":
    main()