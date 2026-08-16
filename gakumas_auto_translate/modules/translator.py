"""
翻译模块，处理翻译相关功能
"""

import json
import os
import re
import shutil

from .utils import GROUP_MANIFEST, merge_groups

# 同组合并后单次请求最多 250 行。DeepSeek V4 Pro 的 thinking 与最终译文
# 共用 max_tokens，因此需要比普通非思考模型更大的预算。
DEFAULT_MIN_MAX_TOKENS = 12288
DEEPSEEK_V4_PRO_MIN_MAX_TOKENS = 65536


def required_max_tokens(model):
    if "deepseek-v4-pro" in (model or "").lower():
        return DEEPSEEK_V4_PRO_MIN_MAX_TOKENS
    return DEFAULT_MIN_MAX_TOKENS


def ensure_max_tokens(env_path):
    """.env 的 MAX_TOKENS 太小会截断合并请求的输出，就地调高并告知。"""
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        text = f.read()
    model_match = re.search(r"^MODEL=(.+?)\s*$", text, re.M)
    model = model_match.group(1).strip() if model_match else ""
    minimum = required_max_tokens(model)
    m = re.search(r"^MAX_TOKENS=(\d+)\s*$", text, re.M)
    current = int(m.group(1)) if m else 0
    if current >= minimum:
        return
    line = f"MAX_TOKENS={minimum}"
    text = re.sub(r"^MAX_TOKENS=.*$", line, text, flags=re.M) if m else \
        text.rstrip("\n") + "\n" + line + "\n"
    with open(env_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"已把 .env 的 MAX_TOKENS 从 {current or '(未设置)'} 调高到 {minimum}"
          f"——当前模型的思考与同组合并译文需要更大的完整输出预算")

def translate_csv_files():
    """处理CSV文件翻译流程"""
    gakumas_dir = "./GakumasPreTranslation"
    
    # 检查Gakumas项目目录是否存在
    if not os.path.exists(gakumas_dir):
        print("未找到GakumasPreTranslation目录，请执行以下操作：")
        print("git clone https://github.com/imas-tools/GakumasPreTranslation.git")
        print("或手动克隆项目到当前目录")
        return False

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
            return False

    ensure_max_tokens(env_path)

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
        print("请确认是否需要执行选项5，或手动清理目录内容后重试")
        return False

    # 准备复制CSV文件
    source_dir = "./todo/untranslated/csv_dict"  # 修改为csv_dict
    target_dir = tmp_dirs[0]  # untranslated目录
    
    # 创建目标目录（如果不存在）
    os.makedirs(target_dir, exist_ok=True)
    
    # 获取待复制文件列表
    csv_files = [f for f in os.listdir(source_dir) if f.endswith(".csv")]
    if not csv_files:
        print("没有需要翻译的CSV文件")
        print("请先执行选项2生成预处理文件")
        return False

    # 执行文件复制；cidol/csprt 的同组段落在此拼成一个 CSV 一次翻完，
    # 否则后段看不到前段，跨段剧情会断——与自动管线共用同一份合并实现。
    print("正在复制翻译文件...")
    manifest = merge_groups(
        [os.path.join(source_dir, f) for f in csv_files], target_dir)
    for filename in sorted(os.listdir(target_dir)):
        print(f"已复制: {filename}")

    # 台账要落盘：菜单3 和菜单4 是两次独立调用，内存里传不过去
    manifest_path = os.path.join("./todo/untranslated", GROUP_MANIFEST)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    if manifest:
        print(f"同组合并 {len(manifest)} 组，台账: {manifest_path}")

    # 输出后续指引
    print("\n请手动执行以下操作：")
    print("1. 进入GakumasPreTranslation目录,在目录下执行yarn命令安装依赖")
    print("2. 根据项目文档配置翻译参数")
    print("3. 在/tmp/untranslated运行翻译脚本'yarn translate:folder'")
    print("4. 完成翻译后返回本程序执行选项4（合并翻译文件）")
    print("翻译输入目录:", os.path.abspath(target_dir))
    print("翻译输出目录:", os.path.abspath(tmp_dirs[1]))
    
    return True
