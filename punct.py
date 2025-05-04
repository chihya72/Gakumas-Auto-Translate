import os
import re
import csv
import string

def extract_punctuation(text):
    """从文本中提取所有标点符号，保留特殊组合"""
    # 首先替换特殊组合为临时标记
    text = re.sub(r'『N\.I\.A』', '___NIA_PLACEHOLDER___', text)
    text = re.sub(r'『Campus mode!!』', '___CAMPUS_MODE_PLACEHOLDER___', text)
    text = re.sub(r'『初』', '___HATSU_PLACEHOLDER___', text)
    text = re.sub(r'『一番星』', '___ICHIBANBOSHI_PLACEHOLDER___', text)
    text = re.sub(r'『H\.I\.F』', '___HIF_PLACEHOLDER___', text)
    
    chinese_punctuation = '。，！？、：；『』「」（）《》'
    punctuation = ''.join(char for char in text if char in string.punctuation + '…' + chinese_punctuation)
    
    # 恢复特殊组合的标记
    punctuation = punctuation.replace('___NIA_PLACEHOLDER___', '『N.I.A』')
    punctuation = punctuation.replace('___CAMPUS_MODE_PLACEHOLDER___', '『Campus mode!!』')
    punctuation = punctuation.replace('___HATSU_PLACEHOLDER___', '『初』')
    punctuation = punctuation.replace('___ICHIBANBOSHI_PLACEHOLDER___', '『一番星』')
    punctuation = punctuation.replace('___HIF_PLACEHOLDER___', '『H.I.F』')
    return punctuation

def is_punctuation_correct(jp_punct, cn_punct, jp_original, cn_original):
    """检查中文标点符号是否符合中文使用习惯"""
    incorrect_cases = []
    
    # 预处理：替换特殊组合为占位符
    jp_punct_processed = jp_punct.replace('『N.I.A』', '___NIA_PLACEHOLDER___')
    jp_punct_processed = jp_punct_processed.replace('『Campus mode!!』', '___CAMPUS_MODE_PLACEHOLDER___')
    jp_punct_processed = jp_punct_processed.replace('『初』', '___HATSU_PLACEHOLDER___')
    jp_punct_processed = jp_punct_processed.replace('『一番星』', '___ICHIBANBOSHI_PLACEHOLDER___')
    jp_punct_processed = jp_punct_processed.replace('『H.I.F』', '___HIF_PLACEHOLDER___')
    
    cn_punct_processed = cn_punct.replace('『N.I.A』', '___NIA_PLACEHOLDER___')
    cn_punct_processed = cn_punct_processed.replace('『Campus mode!!』', '___CAMPUS_MODE_PLACEHOLDER___')
    cn_punct_processed = cn_punct_processed.replace('『初』', '___HATSU_PLACEHOLDER___')
    cn_punct_processed = cn_punct_processed.replace('『一番星』', '___ICHIBANBOSHI_PLACEHOLDER___')
    cn_punct_processed = cn_punct_processed.replace('『H.I.F』', '___HIF_PLACEHOLDER___')
    
    # 检查特殊组合的一致性
    # 对于『N.I.A』
    jp_has_nia = '『N.I.A』' in jp_original
    cn_has_nia = '『N.I.A』' in cn_original or '《N.I.A》' in cn_original
    
    if jp_has_nia and not cn_has_nia:
        incorrect_cases.append("应使用日式引号'『』'保持一致; 应使用日式引号'『』'保持一致")
    
    # 对于『Campus mode!!』
    jp_has_campus = '『Campus mode!!』' in jp_original
    cn_has_campus_jp_style = '『Campus mode!!』' in cn_original
    cn_has_campus_cn_style = '《Campus mode!!》' in cn_original
    
    if jp_has_campus and not (cn_has_campus_jp_style or cn_has_campus_cn_style):
        incorrect_cases.append("应使用日式引号'『』'保持一致; 应使用日式引号'『』'保持一致")
    elif jp_has_campus and cn_has_campus_jp_style:
        # 如果中文使用了日式引号而不是书名号，这是一个问题
        incorrect_cases.append("应使用书名号'《》'代替日式引号'『』'")
    
    # 对于『初』
    jp_has_hatsu = '『初』' in jp_original
    cn_has_hatsu_jp_style = '『初』' in cn_original
    cn_has_hatsu_cn_style = '《初》' in cn_original
    
    if jp_has_hatsu and not (cn_has_hatsu_jp_style or cn_has_hatsu_cn_style):
        incorrect_cases.append("应使用日式引号'『』'保持一致; 应使用日式引号'『』'保持一致")
    elif jp_has_hatsu and cn_has_hatsu_jp_style:
        # 如果中文使用了日式引号而不是书名号，这是一个问题
        incorrect_cases.append("应使用书名号'《》'代替日式引号'『』'")
    
    # 对于『一番星』
    jp_has_ichibanboshi = '『一番星』' in jp_original
    cn_has_ichibanboshi = '『一番星』' in cn_original
    
    if jp_has_ichibanboshi and not cn_has_ichibanboshi:
        incorrect_cases.append("应使用日式引号'『』'保持一致")
    
    # 对于『H.I.F』
    jp_has_hif = '『H.I.F』' in jp_original
    cn_has_hif = '『H.I.F』' in cn_original
    
    if jp_has_hif and not cn_has_hif:
        incorrect_cases.append("应使用日式引号'『』'保持一致")
    
    # 检查省略号：日文中的"…"或"..."应在中文中为"……"
    if ('...' in jp_punct_processed or '…' in jp_punct_processed or '..' in jp_punct_processed) and ('...' in cn_punct_processed or '..' in cn_punct_processed) and '……' not in cn_punct_processed:
        incorrect_cases.append("省略号应使用'……'而非'...'")
    
    # 检查句号：日文中的句号"。"在中文中也应使用"。"
    if '。' in jp_punct_processed and '。' not in cn_punct_processed and '.' in cn_punct_processed:
        incorrect_cases.append("句末应使用句号'。'而非英文句点'.'")
    
    # 检查感叹号：确保使用全角感叹号
    if '!' in jp_punct_processed and '!' in cn_punct_processed and '！' not in cn_punct_processed:
        incorrect_cases.append("应使用全角感叹号'！'而非半角'!'")
    
    # 检查问号：确保使用全角问号
    if '?' in jp_punct_processed and '?' in cn_punct_processed and '？' not in cn_punct_processed:
        incorrect_cases.append("应使用全角问号'？'而非半角'?'")
    
    # 检查逗号：日文中的逗号应在中文中使用"，"而非","
    if '、' in jp_punct_processed and ',' in cn_punct_processed and '，' not in cn_punct_processed:
        incorrect_cases.append("应使用全角逗号'，'而非半角','")
    
    # 检查引号：如果日文中有『』引号，中文中也应该使用『』引号
    # 排除已经被替换的特殊组合
    if '『' in jp_punct_processed and '『' not in cn_punct_processed:
        incorrect_cases.append("应使用日式引号'『』'保持一致")
    if '』' in jp_punct_processed and '』' not in cn_punct_processed:
        incorrect_cases.append("应使用日式引号'『』'保持一致")
    
    return incorrect_cases

def process_files():
    # 数据目录路径
    data_dir = "data"
    
    # 输出CSV文件
    output_file = "punctuation_issues.csv"
    
    # 定义CSV列头
    fieldnames = ["文件名", "行号", "原文标点", "译文标点", "问题描述", "原文", "译文"]
    
    # 正则表达式匹配 <r\=原文>译文</r> 格式
    pattern = r'<r\\=([^>]*)>([^<]*)</r>'
    
    # 创建CSV文件并写入标题
    with open(output_file, 'w', encoding='utf-8', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # 遍历data目录下所有txt文件
        for root, _, files in os.walk(data_dir):
            for file in files:
                if file.endswith('.txt'):
                    file_path = os.path.join(root, file)
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            
                            # 处理每一行
                            for line_num, line in enumerate(lines, 1):
                                # 检查行是否以 [message 开头
                                if line.strip().startswith('[message'):
                                    # 查找所有 <r\=原文>译文</r> 的匹配项
                                    matches = re.findall(pattern, line)
                                    
                                    for match in matches:
                                        original_text = match[0]  # 原文
                                        translated_text = match[1]  # 译文
                                        
                                        # 提取原文和译文中的标点符号
                                        original_punctuation = extract_punctuation(original_text)
                                        translated_punctuation = extract_punctuation(translated_text)
                                        
                                        # 检查标点符号使用是否正确
                                        issues = is_punctuation_correct(original_punctuation, translated_punctuation, original_text, translated_text)
                                        
                                        # 如果存在问题，写入CSV
                                        if issues:
                                            writer.writerow({
                                                "文件名": file,
                                                "行号": line_num,
                                                "原文标点": original_punctuation,
                                                "译文标点": translated_punctuation,
                                                "问题描述": "; ".join(issues),
                                                "原文": original_text,
                                                "译文": translated_text
                                            })
                    except Exception as e:
                        print(f"处理文件 {file_path} 时出错: {e}")
    
    print(f"标点符号检查完成，发现的问题已保存到 {output_file}")

if __name__ == "__main__":
    process_files()