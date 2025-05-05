import os
import re
import sys

# ...(之前的读取和错误处理代码保持不变)...

def process_text_file(filepath):
    """
    读取文本文件，查找特定模式 <r\=part1>part2</r>。
    当 part1 恰好有 4 个 '…' 且 part2 有超过 4 个 '…' 时，
    修改 part2，将其中每一个 '…+' 序列替换为 '……'。
    """
    try:
        # --- 读取文件内容 (同上一个版本) ---
        content = None
        detected_encoding = None
        try:
            with open(filepath, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            detected_encoding = 'utf-8-sig'
        except UnicodeDecodeError:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                detected_encoding = 'utf-8'
            except UnicodeDecodeError as e_utf8:
                try:
                    default_encoding = sys.getdefaultencoding()
                    with open(filepath, 'r', encoding=default_encoding) as f:
                        content = f.read()
                    detected_encoding = default_encoding
                    print(f"警告: 文件 {os.path.basename(filepath)} 使用非标准编码 {default_encoding} 读取。")
                except Exception as e_default:
                    print(f"错误: 无法以 UTF-8 或默认编码读取文件 {os.path.basename(filepath)}。跳过。错误: {e_utf8}, {e_default}")
                    return "error"
        except Exception as e:
             print(f"读取文件时发生错误 {os.path.basename(filepath)}: {e}")
             return "error"

        if content is None:
             return "error"

        original_content = content

        # --- 定义正则表达式 ---
        pattern = re.compile(r'(<r\\=.*?>)(.*?)(<\/r>)', re.DOTALL)
        ellipsis_char = '…' # 标准省略号 U+2026

        def replace_logic(match):
            """
            替换函数，根据最新理解的规则修改匹配项的中间部分。
            """
            part1 = match.group(1)  # <r\=...>
            part2 = match.group(2)  # 中间内容
            part3 = match.group(3)  # </r>

            # 计算 part1 和 part2 中的省略号字符总数
            n1 = part1.count(ellipsis_char)
            n2 = part2.count(ellipsis_char)

            # --- 核心条件判断 ---
            # 只有当 part1 恰好有 4 个省略号，且 part2 超过 4 个时才处理
            if n1 == 4 and n2 > 4:
                # 定义固定的替换内容：两个省略号
                replacement_ellipsis = ellipsis_char * 2  # '……'

                # 在 part2 中，将所有连续的省略号序列 (…+) 替换为 '……'
                modified_part2 = re.sub(r'…+', replacement_ellipsis, part2)

                # 返回修改后的完整匹配项
                return part1 + modified_part2 + part3
            else:
                # 不满足条件，返回原始匹配项，不做修改
                return match.group(0)

        # --- 执行替换 ---
        new_content = pattern.sub(replace_logic, content)

        # --- 写回文件 (仅当内容有变化时) ---
        # (写回逻辑同上一个版本，确保使用检测到的编码或回退到UTF-8)
        if new_content != original_content:
            try:
                write_encoding = detected_encoding if detected_encoding else 'utf-8'
                if write_encoding == 'utf-8-sig':
                     with open(filepath, 'w', encoding='utf-8-sig') as f:
                         f.write(new_content)
                else:
                    # 对于非BOM的UTF-8或其他编码
                    with open(filepath, 'w', encoding=write_encoding, errors='replace') as f: # 加一个errors参数更安全
                        f.write(new_content)

                print(f"已处理并更新文件: {os.path.basename(filepath)}")
                return "modified"
            except Exception as e:
                print(f"写入文件时发生错误 {os.path.basename(filepath)} (编码: {write_encoding}): {e}")
                try:
                    print(f"尝试以 UTF-8 编码回退写入...")
                    with open(filepath, 'w', encoding='utf-8', errors='replace') as f:
                        f.write(new_content)
                    print(f"已处理并以 UTF-8 更新文件: {os.path.basename(filepath)}")
                    return "modified"
                except Exception as e_fallback:
                    print(f"以 UTF-8 回退写入失败: {e_fallback}")
                    return "error"
        else:
            # print(f"文件无需修改: {os.path.basename(filepath)}")
            return "no_change"

    except FileNotFoundError:
        print(f"错误: 文件未找到 - {filepath}")
        return "error"
    except Exception as e:
        print(f"处理文件 {os.path.basename(filepath)} 时发生未知错误: {e}")
        return "error"

# --- 主程序逻辑 (同上一个版本) ---
if __name__ == "__main__":
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        script_dir = os.getcwd()
        print("警告: 无法确定脚本目录，将使用当前工作目录。")

    data_dir = os.path.join(script_dir, 'data')

    if not os.path.isdir(data_dir):
        print(f"错误: 文件夹 'data' 在以下位置未找到: {data_dir}")
        sys.exit(1)

    print(f"开始处理目录: {data_dir}")
    total_files = 0
    modified_files = 0
    no_change_files = 0
    error_files = 0

    for filename in os.listdir(data_dir):
        if filename.lower().endswith('.txt'):
            total_files += 1
            filepath = os.path.join(data_dir, filename)
            print(f"--- 正在处理: {filename} ---")
            result = process_text_file(filepath)

            if result == "modified":
                modified_files += 1
            elif result == "no_change":
                no_change_files += 1
            else: # result == "error"
                error_files += 1

    print("-" * 40)
    print("处理完成。")
    print(f"总共检查文件数: {total_files}")
    print(f"已修改文件数:   {modified_files}")
    print(f"无需修改文件数: {no_change_files}")
    print(f"处理失败文件数: {error_files}")
    print("-" * 40)
    # input("按 Enter 键退出...")
