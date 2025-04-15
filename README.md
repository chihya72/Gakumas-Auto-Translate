# 学园偶像大师剧情机翻工具

这是一个用于管理学园偶像大师（Gakuen Idolmaster）游戏文本翻译的命令行工具。该工具提供了一个完整的工作流程，从游戏解包文件中提取文本，准备翻译文件，使用翻译API进行翻译，然后将翻译内容合并回游戏文件格式。

## 功能特点

- 检测新增未翻译文本文件
- 将游戏文本预处理为CSV格式以便翻译
- 与外部翻译工具集成
- 支持纯中文或中日双语格式
- 自动化文件管理和目录结构
- 翻译完成后的清理和文件整理

## 前置要求

1. Python 3.6+
2. 已解包的游戏文本文件（使用[Gakuen-idolmaster-ab-decrypt](https://github.com/nijinekoyo/Gakuen-idolmaster-ab-decrypt.git)工具）
3. Git（用于克隆翻译工具仓库）
4. [SCPreTranslation](https://github.com/ShinyGroup/SCPreTranslation.git)工具（在脚本中被称为GakumasPreTranslation）
5. Node.js和Yarn（用于运行翻译工具）

## 安装与设置

1. 克隆本仓库到本地

   ```
   bash复制git clone [您的仓库URL]
   cd [仓库文件夹]
   ```

2. 克隆并准备翻译工具

   ```
   bash
   
   
   复制
   git clone https://github.com/ShinyGroup/SCPreTranslation.git GakumasPreTranslation
   ```

3. 解包游戏文件（如果尚未完成）

   ```
   bash复制# 请参考 https://github.com/nijinekoyo/Gakuen-idolmaster-ab-decrypt.git
   # 解包后的文件应存放在您指定的dump_txt目录中
   ```

## 使用流程

1. **配置并检测所需目录**（选项9）
   - 设置数据存储目录
   - 配置dump_txt文件路径（游戏解包文件的位置）
2. **检查新增未翻译文本**（选项1）
   - 比较dump_txt和data目录，找出需要翻译的新文件
   - 自动创建todo目录结构并复制新文件
3. **预处理文本为CSV**（选项2）
   - 解析原始游戏文本文件
   - 提取对话和选项文本
   - 生成含有原文和空翻译字段的CSV文件
4. **翻译CSV文件**（选项3）
   - 准备GakumasPreTranslation环境
   - 复制待翻译文件到翻译工具目录
   - 提供使用翻译工具的指导
5. **合并翻译文件**（选项4）
   - 检查翻译完成情况
   - 支持两种合并模式:
     - 纯中文（仅保留翻译内容）
     - 中日双语（保留原文和翻译）
   - 生成最终的翻译后txt文件
6. **完成并清理临时文件**（选项5）
   - 将翻译后的文件复制到data目录
   - 清理todo和翻译工具临时目录

## 翻译工具配置

GakumasPreTranslation（即SCPreTranslation）需要进行以下配置：

1. 进入GakumasPreTranslation目录
2. 复制.env.sample为.env文件
3. 编辑.env文件，配置您的翻译API密钥（如DeepL、Google等）
4. 运行`yarn`安装依赖
5. 按照工具文档配置翻译参数
6. 使用`yarn translate:folder`命令执行翻译

## 文件结构

```
bash复制./
├── data/                   # 存储已翻译文件的目录
├── dump_txt/               # 游戏解包文件目录
├── todo/                   # 工作流临时文件
│   ├── untranslated/       
│   │   ├── txt/            # 未翻译的原始文本
│   │   └── csv/            # 待翻译的CSV文件
│   └── translated/         
│       ├── csv/            # 已翻译的CSV文件
│       └── txt/            # 合并翻译后的游戏文本
└── GakumasPreTranslation/  # 翻译工具目录
```

## 注意事项

1. 游戏文本需要先使用[Gakuen-idolmaster-ab-decrypt](https://github.com/nijinekoyo/Gakuen-idolmaster-ab-decrypt.git)工具进行解包
2. 翻译工具使用的是[SCPreTranslation](https://github.com/ShinyGroup/SCPreTranslation.git)项目，需要重命名为GakumasPreTranslation
3. 翻译API需要自行申请密钥并在.env文件中配置
4. 中日双语模式会用特殊格式标记原文和译文，可能需要游戏支持此格式

## 常见问题

- **找不到dump_txt目录**：请确保您已正确解包游戏文件，并在选项9中配置正确的路径
- **翻译工具报错**：请检查.env配置是否正确，API密钥是否有效
- **合并后的文本格式错误**：根据游戏支持的格式选择合适的合并模式（纯中文或中日双语）

## 贡献与反馈

如发现问题或有改进建议，请提交Issue或Pull Request到本项目的仓库。