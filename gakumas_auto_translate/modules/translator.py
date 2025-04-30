"""
翻译模块，处理翻译相关功能
"""

import os
import shutil

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
    
    return True