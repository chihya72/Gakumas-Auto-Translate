"""
翻译模块，处理翻译相关功能
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import shutil
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, ensure_paths_exist

# 获取日志记录器
logger = get_logger("translator")

def translate_csv_files():
    """处理CSV文件翻译流程"""
    # 获取路径
    gakumas_dir = get_path("gakumas_dir")
    untranslated_dir = get_path("gakumas_tmp_untranslated")
    translated_dir = get_path("gakumas_tmp_translated")
    source_dir = get_path("todo_untranslated_csv_dict")
    
    # 检查Gakumas项目目录是否存在
    if not os.path.exists(gakumas_dir):
        logger.error("未找到GakumasPreTranslation目录，请执行以下操作：")
        logger.error("git clone https://github.com/imas-tools/GakumasPreTranslation.git")
        logger.error("或手动克隆项目到当前目录")
        return False

    # 检查.env文件是否存在
    env_path = os.path.join(gakumas_dir, ".env")
    if not os.path.exists(env_path):
        sample_env = os.path.join(gakumas_dir, ".env.sample")
        if os.path.exists(sample_env):
            try:
                shutil.copy(sample_env, env_path)
                logger.info("已创建.env文件，请修改以下内容：")
                logger.info("1. 配置翻译API密钥（如DEEPL_AUTH_KEY）")
                logger.info("2. 设置翻译引擎参数")
                logger.info(f"文件路径: {os.path.abspath(env_path)}")
            except Exception as e:
                logger.error(f"创建.env文件失败: {e}")
                return False
        else:
            logger.error("错误：缺失.env.sample文件，请检查GakumasPreTranslation项目完整性")
            return False

    # 确保临时目录存在
    ensure_paths_exist(["gakumas_tmp_untranslated", "gakumas_tmp_translated"])
    
    # 检查目录是否为空
    dirs_not_empty = []
    for dir_path in [untranslated_dir, translated_dir]:
        try:
            if os.path.exists(dir_path) and len(os.listdir(dir_path)) > 0:
                dirs_not_empty.append(dir_path)
        except Exception as e:
            logger.error(f"检查目录失败 {dir_path}: {e}")
            return False
    
    if dirs_not_empty:
        logger.warning("以下目录需要清空才能继续操作：")
        for d in dirs_not_empty:
            logger.warning(f"- {os.path.abspath(d)}")
        logger.warning("请确认是否需要执行选项5，或手动清理目录内容后重试")
        return False

    # 获取待复制文件列表
    try:
        csv_files = [f for f in os.listdir(source_dir) if f.endswith(".csv")]
    except FileNotFoundError:
        logger.error(f"源目录不存在: {source_dir}")
        return False
    except PermissionError:
        logger.error(f"无权限访问源目录: {source_dir}")
        return False
    except Exception as e:
        logger.error(f"读取源目录失败: {e}")
        return False
    
    if not csv_files:
        logger.warning("没有需要翻译的CSV文件")
        logger.warning("请先执行选项2生成预处理文件")
        return False

    # 执行文件复制
    logger.info("正在复制翻译文件...")
    copied_count = 0
    for filename in csv_files:
        try:
            src = os.path.join(source_dir, filename)
            dst = os.path.join(untranslated_dir, filename)
            shutil.copy2(src, dst)
            logger.info(f"已复制: {filename}")
            copied_count += 1
        except FileNotFoundError:
            logger.error(f"源文件不存在: {src}")
        except PermissionError:
            logger.error(f"无权限复制文件: {src} -> {dst}")
        except Exception as e:
            logger.error(f"复制文件失败 {filename}: {e}")
    
    if copied_count == 0:
        logger.error("没有成功复制任何文件")
        return False

    # 输出后续指引
    logger.info("\n请手动执行以下操作：")
    logger.info("1. 进入GakumasPreTranslation目录,在目录下执行yarn命令安装依赖")
    logger.info("2. 根据项目文档配置翻译参数")
    logger.info("3. 在/tmp/untranslated运行翻译脚本'yarn translate:folder'")
    logger.info("4. 完成翻译后返回本程序执行选项4（合并翻译文件）")
    logger.info(f"翻译输入目录: {os.path.abspath(untranslated_dir)}")
    logger.info(f"翻译输出目录: {os.path.abspath(translated_dir)}")
    
    return True
