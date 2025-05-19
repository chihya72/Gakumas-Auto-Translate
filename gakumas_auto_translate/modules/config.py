"""
配置模块，负责处理程序配置和目录设置
改进版：增加异常处理、日志记录和路径灵活性
"""

import os
import json
from gakumas_auto_translate.modules.logger import get_logger
from gakumas_auto_translate.modules.paths import get_path, get_project_paths, ensure_paths_exist
from gakumas_auto_translate.modules.utils import create_sample_dictionary

# 获取日志记录器
logger = get_logger("config")

class ConfigManager:
    """配置管理类"""
    
    def __init__(self):
        """初始化配置管理器"""
        self.config = {}
        self.config_file = get_path("config_file")
        self.dump_txt_path = None
        self.load_config()
    
    def load_config(self):
        """从配置文件加载设置"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                    
                if 'dump_txt_path' in self.config:
                    if os.path.exists(self.config['dump_txt_path']):
                        self.dump_txt_path = self.config['dump_txt_path']
                        logger.info(f"已加载dump_txt_path配置: {self.dump_txt_path}")
                        return True
                    else:
                        logger.warning(f"配置文件中的dump_txt_path不存在: {self.config['dump_txt_path']}")
                else:
                    logger.warning("配置文件中缺少dump_txt_path设置")
            except json.JSONDecodeError as e:
                logger.error(f"配置文件格式错误: {e}")
            except Exception as e:
                logger.error(f"读取配置文件时出错: {e}")
        else:
            logger.info(f"配置文件不存在: {self.config_file}")
        
        return False
    
    def save_config(self):
        """保存设置到配置文件"""
        try:
            # 确保配置文件目录存在
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # 更新配置
            self.config['dump_txt_path'] = self.dump_txt_path
            
            # 写入配置文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=4)
            
            logger.info(f"配置已保存到: {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件时出错: {e}")
            return False
    
    def configure_directories(self):
        """配置并检测所需目录"""
        # 确保基本目录结构存在
        created_paths = ensure_paths_exist(["data_dir"])
        if created_paths:
            logger.info(f"已创建以下目录: {', '.join(created_paths)}")
        
        # 配置dump_txt目录
        while True:
            path = input("请输入dump_txt目录路径（留空使用默认./dump_txt）: ").strip()
            temp_path = path if path else "./dump_txt"
            temp_path = os.path.abspath(temp_path)
            
            if not os.path.exists(temp_path):
                choice = input(f"目录不存在: {temp_path}，是否创建？(y/n): ").lower()
                if choice == 'y':
                    try:
                        os.makedirs(temp_path, exist_ok=True)
                        logger.info(f"已创建目录: {temp_path}")
                        self.dump_txt_path = temp_path
                        self.save_config()
                        break
                    except Exception as e:
                        logger.error(f"创建目录失败: {e}")
                        continue
                else:
                    continue
            else:
                logger.info(f"使用已存在的目录: {temp_path}")
                self.dump_txt_path = temp_path
                self.save_config()
                break
        
        # 检查字典文件
        dict_file = get_path("dict_file")
        if not os.path.exists(dict_file):
            # 如果不存在，创建一个示例字典文件
            create_sample_dictionary(dict_file)
            logger.info(f"已创建示例字典文件: {dict_file}")
            logger.info("请编辑此文件添加需要替换的人名和称谓")
        
        return self.dump_txt_path
    
    def get_dump_txt_path(self):
        """获取dump_txt路径"""
        return self.dump_txt_path
    
    def set_dump_txt_path(self, path):
        """设置dump_txt路径"""
        if os.path.exists(path):
            self.dump_txt_path = path
            self.save_config()
            logger.info(f"已设置dump_txt_path: {path}")
            return True
        else:
            logger.error(f"路径不存在: {path}")
            return False

# 创建全局配置管理器实例
config_manager = ConfigManager()

# 导出函数，保持与原模块兼容
def load_config():
    """从配置文件加载设置"""
    return config_manager.load_config()

def save_config():
    """保存设置到配置文件"""
    return config_manager.save_config()

def configure_directories():
    """配置并检测所需目录"""
    return config_manager.configure_directories()

def get_dump_txt_path():
    """获取dump_txt路径"""
    return config_manager.get_dump_txt_path()

def set_dump_txt_path(path):
    """设置dump_txt路径"""
    return config_manager.set_dump_txt_path(path)
