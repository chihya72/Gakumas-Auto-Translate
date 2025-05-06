import os
import csv
import re
from collections import defaultdict

# --- 正则表达式 ---

# === 用于双语文件 (BILINGUAL) ===
BILINGUAL_R_TAG_EXTRACTOR_RE = re.compile(r"<r\\=[\s\S]*?>([\s\S]*?)(?:</r>|/r>)")
BILINGUAL_MESSAGE_RE = re.compile(r"\[message text=([\s\S]+?) name=[\s\S]*? clip=.*?\"_startTime\":([\d\.]+).*?\]")
BILINGUAL_NARRATION_RE = re.compile(r"\[narration text=([\s\S]+?) (?:hide=true )?clip=.*?\"_startTime\":([\d\.]+).*?\]")
BILINGUAL_CHOICE_GROUP_RE = re.compile(r"\[choicegroup choices=\[(.*?)\] clip=.*?\"_startTime\":([\d\.]+).*?\]")
CHOICE_TEXT_EXTRACTOR_RE = re.compile(r"choice text=([\s\S]*?)(?=\] choices=\[choice text=|$)")


# === 用于日文原文文件 (ORIGINAL JAPANESE) ===
ORIGINAL_MESSAGE_RE = re.compile(
    r"\[message text=([\s\S]+?)"
    r"\s+name=\s*(\S+)"  # 允许等号后有空格, 然后捕获非空格字符
    r"[\s\S]*?" # 匹配 name 和 clip 之间的任何其他属性 (非贪婪)
    r"\s*clip=.*?\"_startTime\":([\d\.]+).*?\]"
)
ORIGINAL_NARRATION_RE = re.compile(r"\[narration text=([\s\S]+?) (?:hide=true )?clip=.*?\"_startTime\":([\d\.]+).*?\]")
ORIGINAL_CHOICE_GROUP_RE = re.compile(r"\[choicegroup choices=\[(.*?)\] clip=.*?\"_startTime\":([\d\.]+).*?\]")
ORIGINAL_CHOICE_TEXT_EXTRACTOR_RE = re.compile(r"choice text=([\s\S]*?)(?=\] choices=\[choice text=|$)")


def get_raw_japanese_text(raw_text_content_from_original):
    if raw_text_content_from_original is None:
        return ""
    # \n 字符在从文件读取时已是字面量，strip() 不会改变它们
    return raw_text_content_from_original.strip()


def parse_original_japanese_file_content(filepath):
    parsed_data = {
        "messages": defaultdict(list),
        "narrations": defaultdict(list),
        "choices": {}
    }

    if not os.path.exists(filepath):
        print(f"警告: 日文原文件未找到: {filepath}")
        return parsed_data

    try:
        with open(filepath, 'r', encoding='utf-8') as f_orig:
            for line_orig in f_orig:
                line_orig = line_orig.strip()

                match_msg = ORIGINAL_MESSAGE_RE.match(line_orig)
                if match_msg:
                    raw_jp_text_content = match_msg.group(1)
                    jp_name = match_msg.group(2).strip()
                    start_time = match_msg.group(3)
                    processed_jp_text = get_raw_japanese_text(raw_jp_text_content) # \n 已保留
                    parsed_data["messages"][start_time].append({"text": processed_jp_text, "name": jp_name})
                    continue

                match_nar = ORIGINAL_NARRATION_RE.match(line_orig)
                if match_nar:
                    raw_jp_text_content = match_nar.group(1)
                    start_time_nar = match_nar.group(2)
                    processed_jp_text = get_raw_japanese_text(raw_jp_text_content) # \n 已保留
                    parsed_data["narrations"][start_time_nar].append(processed_jp_text)
                    continue

                match_cg = ORIGINAL_CHOICE_GROUP_RE.match(line_orig)
                if match_cg:
                    jp_choices_str = match_cg.group(1)
                    start_time_cg = match_cg.group(2)
                    
                    extracted_jp_choices = [
                        get_raw_japanese_text(choice.strip()) # \n 已保留
                        for choice in ORIGINAL_CHOICE_TEXT_EXTRACTOR_RE.findall(jp_choices_str)
                    ]
                    if start_time_cg in parsed_data["choices"] and extracted_jp_choices:
                        print(f"警告: 在日文原文件 {filepath} 中发现重复的 startTime {start_time_cg} (choice groups)。将使用后找到的。")
                    if extracted_jp_choices:
                        parsed_data["choices"][start_time_cg] = extracted_jp_choices
                    elif jp_choices_str.strip() and "choice text=" in jp_choices_str :
                         print(f"调试: 日文原文件 {filepath}, startTime {start_time_cg}: 未能从 '{jp_choices_str}' 解析出日文选项，尽管包含 'choice text='。")
    except Exception as e:
        print(f"错误: 读取或解析日文原文件 {filepath} 时发生错误: {e}")
    return parsed_data


def extract_chinese_from_bilingual_text_node(bilingual_text_content):
    chinese_parts = []
    if bilingual_text_content:
        matches = BILINGUAL_R_TAG_EXTRACTOR_RE.findall(bilingual_text_content)
        for cn_part in matches:
            # cn_part 直接来自正则匹配，其内部的 \n 已经是字面量
            chinese_parts.append(cn_part) 
    # MODIFIED: 使用 "\\n" (字面 \n) 而不是 "\n" (换行符) 来连接片段
    return "\\n".join(chinese_parts)


def process_game_scripts_main(bilingual_root_dir, original_root_dir, output_directory_path):
    sequential_match_counters = {
        "messages": defaultdict(int),
        "narrations": defaultdict(int)
    }
    
    # 添加统计计数器
    skipped_files = []
    processed_files = []
    failed_files = []

    for filename in os.listdir(bilingual_root_dir):
        if not filename.endswith(".txt"):
            continue

        bilingual_file_path = os.path.join(bilingual_root_dir, filename)
        original_file_path = os.path.join(original_root_dir, filename)
        
        base_name, _ = os.path.splitext(filename)
        output_csv_file_for_this_file = os.path.join(output_directory_path, f"{base_name}.csv")

        # 检查CSV文件是否已存在，如果存在则跳过处理
        if os.path.exists(output_csv_file_for_this_file):
            print(f"跳过处理文件: {filename} -> CSV文件已存在: {output_csv_file_for_this_file}")
            skipped_files.append(filename)
            continue

        print(f"正在处理文件: {filename} -> 输出到: {output_csv_file_for_this_file}")

        original_jp_data = parse_original_japanese_file_content(original_file_path)
        if not any(original_jp_data.values()):
             print(f"警告: 日文原文件 {original_file_path} 为空或无法解析。对于 {filename}，日文文本和说话人名称将缺失。")

        current_file_dialogue_rows = []
        for key in sequential_match_counters:
            sequential_match_counters[key].clear()
        
        line_num_in_bilingual_file = 0
        success = False

        try:
            with open(bilingual_file_path, 'r', encoding='utf-8') as f_bilingual:
                for line_num_in_bilingual_file, bilingual_line in enumerate(f_bilingual, 1):
                    bilingual_line = bilingual_line.strip()
                    jp_text_final = "[日文原文缺失]"
                    trans_text_final = "[中文翻译缺失]"
                    speaker_name_final = "[说话人名称缺失]" 

                    match_bi_msg = BILINGUAL_MESSAGE_RE.match(bilingual_line)
                    if match_bi_msg:
                        bilingual_text_attr_for_cn = match_bi_msg.group(1) # text=的原始内容
                        msg_start_time = match_bi_msg.group(2)

                        # 检查原始文本中是否存在<r\=...>标签
                        if BILINGUAL_R_TAG_EXTRACTOR_RE.search(bilingual_text_attr_for_cn):
                            extracted_cn_text = extract_chinese_from_bilingual_text_node(bilingual_text_attr_for_cn)
                            # 如果提取结果非空 (即使是多个空<r>标签连接产生的"\n"), 则使用它
                            if extracted_cn_text: 
                                trans_text_final = extracted_cn_text
                            else: # <r>标签存在但提取内容为空 (例如 <r\=...></r>)
                                print(f"信息 (双语 {filename} 行 {line_num_in_bilingual_file}): Message (startTime: {msg_start_time}) <r>标签存在但未提取到中文内容: '{bilingual_text_attr_for_cn[:50]}...'")
                                # trans_text_final 保持 "[中文翻译缺失]"
                        else: # 不存在 <r\=...> 标签，直接使用 text= 的内容作为中文
                            if bilingual_text_attr_for_cn is not None:
                                # .strip() 清除两端空白, \n 已是字面量
                                cleaned_direct_text = bilingual_text_attr_for_cn.strip()
                                if cleaned_direct_text:
                                    trans_text_final = cleaned_direct_text
                                # 如果 cleaned_direct_text 为空, trans_text_final 保持 "[中文翻译缺失]"
                        
                        original_jp_messages_at_time = original_jp_data["messages"].get(msg_start_time, [])
                        current_jp_idx = sequential_match_counters["messages"][msg_start_time]

                        if original_jp_messages_at_time and current_jp_idx < len(original_jp_messages_at_time):
                            jp_message_obj = original_jp_messages_at_time[current_jp_idx]
                            jp_text_final = jp_message_obj["text"] # \n 已保留
                            speaker_name_final = jp_message_obj["name"] 
                            sequential_match_counters["messages"][msg_start_time] += 1
                        else:
                            if trans_text_final != "[中文翻译缺失]" or \
                               (bilingual_text_attr_for_cn is not None and bilingual_text_attr_for_cn.strip()):
                                print(f"警告 (双语 {filename} 行 {line_num_in_bilingual_file}): 未能在日文原文件中找到 startTime {msg_start_time} 的第 {current_jp_idx + 1} 个 message (日文原文或说话人名称将缺失)。")
                        
                        current_file_dialogue_rows.append(["0000000000000", speaker_name_final, jp_text_final, trans_text_final])
                        continue

                    match_bi_nar = BILINGUAL_NARRATION_RE.match(bilingual_line)
                    if match_bi_nar:
                        bilingual_text_attr_for_cn = match_bi_nar.group(1)
                        nar_start_time = match_bi_nar.group(2)
                        speaker_name_final = "__narration__" 

                        if BILINGUAL_R_TAG_EXTRACTOR_RE.search(bilingual_text_attr_for_cn):
                            extracted_cn_text = extract_chinese_from_bilingual_text_node(bilingual_text_attr_for_cn)
                            if extracted_cn_text:
                                trans_text_final = extracted_cn_text
                            else:
                                print(f"信息 (双语 {filename} 行 {line_num_in_bilingual_file}): Narration (startTime: {nar_start_time}) <r>标签存在但未提取到中文内容: '{bilingual_text_attr_for_cn[:50]}...'")
                        else:
                            if bilingual_text_attr_for_cn is not None:
                                cleaned_direct_text = bilingual_text_attr_for_cn.strip()
                                if cleaned_direct_text:
                                    trans_text_final = cleaned_direct_text
                        
                        original_jp_narrations_at_time = original_jp_data["narrations"].get(nar_start_time, [])
                        current_jp_idx = sequential_match_counters["narrations"][nar_start_time]

                        if original_jp_narrations_at_time and current_jp_idx < len(original_jp_narrations_at_time):
                            jp_text_final = original_jp_narrations_at_time[current_jp_idx] # \n 已保留
                            sequential_match_counters["narrations"][nar_start_time] += 1
                        else:
                            if trans_text_final != "[中文翻译缺失]" or \
                               (bilingual_text_attr_for_cn is not None and bilingual_text_attr_for_cn.strip()):
                                print(f"警告 (双语 {filename} 行 {line_num_in_bilingual_file}): 未能在日文原文件中找到 startTime {nar_start_time} 的第 {current_jp_idx + 1} 个 narration。")

                        current_file_dialogue_rows.append(["narration", speaker_name_final, jp_text_final, trans_text_final])
                        continue

                    match_bi_cg = BILINGUAL_CHOICE_GROUP_RE.match(bilingual_line)
                    if match_bi_cg:
                        bilingual_choices_text_attr = match_bi_cg.group(1)
                        cg_start_time = match_bi_cg.group(2)
                        speaker_name_final = "" 

                        chinese_choices_list = [
                            choice.strip() # \n 已保留
                            for choice in CHOICE_TEXT_EXTRACTOR_RE.findall(bilingual_choices_text_attr)
                        ]
                        
                        if not chinese_choices_list and "choice text=" in bilingual_choices_text_attr:
                            print(f"警告 (双语 {filename} 行 {line_num_in_bilingual_file}): 未能从 '{bilingual_choices_text_attr}' 解析出中文选项 (startTime: {cg_start_time})")

                        japanese_choices_list = original_jp_data["choices"].get(cg_start_time, []) # \n 已保留

                        if not japanese_choices_list and chinese_choices_list:
                             print(f"警告 (双语 {filename} 行 {line_num_in_bilingual_file}): 未能在日文原文件中找到 startTime {cg_start_time} 的匹配日文选项组。中文选项将保留。")

                        max_len = max(len(chinese_choices_list), len(japanese_choices_list))
                        if len(chinese_choices_list) != len(japanese_choices_list) and max_len > 0 :
                            print(f"注意 (双语 {filename} 行 {line_num_in_bilingual_file}): ChoiceGroup (startTime: {cg_start_time}) 选项数量不匹配。中文: {len(chinese_choices_list)}, 日文: {len(japanese_choices_list)}。")

                        if max_len == 0 and "choice text=" in bilingual_choices_text_attr:
                            current_file_dialogue_rows.append(["select", speaker_name_final, "[日文解析错误或缺失]", "[中文解析错误]"])
                        else:
                            for i in range(max_len):
                                jp_choice = japanese_choices_list[i] if i < len(japanese_choices_list) else "[日文选项缺失]"
                                cn_choice = chinese_choices_list[i] if i < len(chinese_choices_list) else "[中文选项缺失]"
                                current_file_dialogue_rows.append(["select", speaker_name_final, jp_choice, cn_choice])
                        continue
            
            all_rows_for_this_csv = []
            all_rows_for_this_csv.append(["id", "name", "text", "trans"])
            all_rows_for_this_csv.extend(current_file_dialogue_rows)
            all_rows_for_this_csv.append(["info", filename, "", ""])
            all_rows_for_this_csv.append(["译者", "Pro/deepseek-ai/DeepSeek-V3", "", ""])

            try:
                with open(output_csv_file_for_this_file, 'w', newline='', encoding='utf-8-sig') as f_out:
                    writer = csv.writer(f_out)
                    writer.writerows(all_rows_for_this_csv)
                if current_file_dialogue_rows: 
                    print(f"CSV文件已成功生成: {output_csv_file_for_this_file}")
                    processed_files.append(filename)
                    success = True
                elif os.path.exists(output_csv_file_for_this_file):
                    print(f"已为 {filename} 生成包含info/译者信息的CSV: {output_csv_file_for_this_file} (无对话内容)")
                    processed_files.append(filename)
                    success = True

            except Exception as e:
                print(f"写入CSV文件 {output_csv_file_for_this_file} 时发生错误: {e}")
                failed_files.append((filename, f"写入CSV文件时错误: {e}"))

            if not current_file_dialogue_rows:
                 if not os.path.exists(output_csv_file_for_this_file):
                    print(f"信息: 文件 {filename} (双语) 未解析出任何有效数据行，也未生成CSV。")
                    if not success:
                        failed_files.append((filename, "未解析出任何有效数据行"))

        except FileNotFoundError:
            print(f"错误: 双语文件未找到: {bilingual_file_path}")
            failed_files.append((filename, "双语文件未找到"))
        except Exception as e:
            line_num_str = str(line_num_in_bilingual_file) if 'line_num_in_bilingual_file' in locals() and line_num_in_bilingual_file > 0 else 'N/A'
            print(f"处理双语文件 {filename} (行 {line_num_str}) 时发生严重错误: {e}")
            failed_files.append((filename, f"行 {line_num_str} 处理错误: {e}"))
            import traceback
            traceback.print_exc()
    
    # 输出统计信息
    print("\n========== 处理统计 ==========")
    print(f"总计跳过文件数: {len(skipped_files)} 个")
    print(f"成功处理文件数: {len(processed_files)} 个")
    print(f"处理失败文件数: {len(failed_files)} 个")
    
    # 只有处理失败的文件才显示详细列表
    if failed_files:
        print("\n处理失败的文件列表:")
        for i, (filename, reason) in enumerate(failed_files, 1):
            print(f"  {i}. {filename} - 原因: {reason}")
    
    print("\n所有文件处理完毕。")


if __name__ == "__main__":
    # --- 请确保将以下路径替换为您的实际路径 ---
    bilingual_files_directory = r"D:\GIT\Gakumas-Auto-Translate\data" 
    original_japanese_files_directory = r"D:\GIT\Gakuen-idolmaster-ab-decrypt\output\resource\txt" 
    output_csv_main_directory = r"D:\GIT\Gakumas-Auto-Translate\csv_data"
    # --- 路径替换结束 ---

    if not os.path.isdir(bilingual_files_directory):
        print(f"错误: 双语文件目录不存在 -> {bilingual_files_directory}")
    elif not os.path.isdir(original_japanese_files_directory):
        print(f"错误: 日文原文文件目录不存在 -> {original_japanese_files_directory}")
    else:
        if not os.path.exists(output_csv_main_directory):
            try:
                os.makedirs(output_csv_main_directory)
                print(f"创建输出目录: {output_csv_main_directory}")
            except OSError as err:
                print(f"错误: 无法创建输出目录 {output_csv_main_directory} ({err})")
                exit(1) 
        
        process_game_scripts_main(bilingual_files_directory, original_japanese_files_directory, output_csv_main_directory)
