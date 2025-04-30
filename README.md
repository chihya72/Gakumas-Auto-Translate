# Gakumas Auto Translate

一个用于自动翻译《学园偶像大师》（Gakuen Idolmaster）游戏文本的工具包。本工具提供完整的文本翻译工作流程，从游戏解包文件中提取文本，到翻译处理，再到将翻译内容合并回游戏文件格式。

## 功能特点

- ✅ **检测新增文本** - 自动检测需要翻译的新文本文件
- 🔄 **文本预处理** - 将游戏文本转换为CSV格式，并进行人名替换
- 🌐 **翻译集成** - 与外部翻译API工具无缝集成
- 📚 **双语支持** - 支持纯中文或中日双语格式
- 🔧 **自动化管理** - 自动化文件管理和目录维护
- 🧹 **清理整理** - 翻译完成后的文件清理和归档

## 项目结构

项目采用模块化设计，提高了代码可维护性和可扩展性：

```
gakumas_auto_translate/       # 主程序包
├── __init__.py               # 包初始化文件
├── main.py                   # 主程序入口
└── modules/                  # 功能模块目录
    ├── __init__.py           # 模块包初始化文件
    ├── checker.py            # 检查新文件模块
    ├── cleaner.py            # 清理和复制模块
    ├── config.py             # 配置管理模块
    ├── merger.py             # 合并翻译文件模块
    ├── preprocessor.py       # 文本预处理模块
    ├── translator.py         # 翻译处理模块
    └── utils.py              # 公共工具函数模块

run.py                        # 快速启动脚本
```

## 文件结构

```
./
├── gakumas_auto_translate/      # 主程序包
├── data/                        # 存储已翻译文件的目录
├── dump_txt/                    # 游戏解包文件目录
├── todo/                        # 工作流临时文件
│   ├── untranslated/       
│   │   ├── txt/                 # 未翻译的原始文本
│   │   └── csv/                 # 待翻译的CSV文件
│   └── translated/         
│       ├── csv/                 # 已翻译的CSV文件
│       └── txt/                 # 合并翻译后的游戏文本
└── GakumasPreTranslation/       # 翻译工具目录
```

## 使用流程

### 初始设置

1. **配置并检测所需目录**（选项9）
   - 设置数据存储目录
   - 配置dump_txt文件路径（游戏解包文件的位置）

### 翻译工作流程

1. **检查新增未翻译文本**（选项1）
   ```
   # 比较dump_txt和data目录，识别需要翻译的新文件
   # 自动创建todo目录结构并复制新文件
   ```

2. **预处理文本为CSV**（选项2）
   ```
   # 解析原始游戏文本文件
   # 提取对话和选项文本
   # 生成含有原文和空翻译字段的CSV文件
   # 应用人名字典进行替换
   ```

3. **翻译CSV文件**（选项3）
   ```
   # 准备GakumasPreTranslation环境
   # 复制待翻译文件到翻译工具目录
   # 使用翻译API处理文本
   ```

4. **合并翻译文件**（选项4）
   ```
   # 检查翻译完成情况
   # 支持纯中文或中日双语格式
   # 生成最终翻译后的txt文件
   ```

5. **完成并清理临时文件**（选项5）
   ```
   # 将翻译后的文件复制到data目录
   # 清理临时文件和目录
   ```

## 人名字典

程序使用`name_dictionary.json`文件进行人名和常见词汇的替换。格式为：

```json
{
  "日文名称1": "中文名称1",
  "日文名称2": "中文名称2"
}
```

## 依赖项

本工具依赖于[GakumasPreTranslation](https://github.com/imas-tools/GakumasPreTranslation)项目（即SCPreTranslation）进行实际翻译操作。请确保已正确安装并配置该项目。

### 前置要求

1. Python 3.6+
2. 已解包的游戏文本文件（使用[Gakuen-idolmaster-ab-decrypt](https://github.com/nijinekoyo/Gakuen-idolmaster-ab-decrypt.git)工具）
3. Git（用于克隆翻译工具仓库）
4. [SCPreTranslation](https://github.com/ShinyGroup/SCPreTranslation.git)工具（在脚本中被称为GakumasPreTranslation）
5. Node.js和Yarn（用于运行翻译工具）

### 安装与设置

1. 克隆本仓库到本地

   ```bash
   git clone [您的仓库URL]
   cd [仓库文件夹]
   ```

2. 克隆并准备翻译工具

   ```bash
   git clone https://github.com/ShinyGroup/SCPreTranslation.git GakumasPreTranslation
   ```

3. 翻译工具配置

   - 进入GakumasPreTranslation目录
   - 复制.env.sample为.env文件
   - 编辑.env文件，配置您的翻译API密钥（如DeepL、Google等）
   - 运行`yarn`安装依赖
   - 按照工具文档配置翻译参数

## 注意事项

- 确保已正确设置翻译API密钥（如DeepL）
- 翻译前请检查人名字典是否需要更新
- 建议定期备份data目录的内容
- 游戏文本需要先使用Gakuen-idolmaster-ab-decrypt工具进行解包
- 中日双语模式会用特殊格式标记原文和译文，可能需要游戏支持此格式

## 常见问题

- **找不到dump_txt目录**：请确保已正确解包游戏文件，并在选项9中配置正确的路径
- **翻译工具报错**：请检查.env配置是否正确，API密钥是否有效
- **合并后的文本格式错误**：根据游戏支持的格式选择合适的合并模式（纯中文或中日双语）

## 贡献与反馈

如发现问题或有改进建议，请提交Issue或Pull Request到本项目的仓库。