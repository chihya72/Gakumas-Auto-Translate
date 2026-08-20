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

## AI 机翻的上下文机制

AI 机翻不再孤立翻译每一批对话。机制分两层：**角色卡与术语表**保证"谁说话像谁、术语一致"，
**分类型的剧情上下文**保证"剧情连不连"。两层正交，各管各的。

分类不靠猜文件名，而是用规范仓库
[gakuen-adapted-stories](https://github.com/imas-tools/gakuen-adapted-stories) 的目录结构生成的
`tools/vendor/story-index.json`（与 [gakumas-viewer](https://github.com/chihya72/gakumas-viewer)
同源的分类体系），每个扁平文件名都映射到标准分类与剧情组。

### 角色卡与术语表（所有类型一律加载）

- **角色卡** `tools/vendor/character-cards.json` —— 16 个重点角色，覆盖 `csv_data` 人工译文里
  95% 的台词。记录自称、敬语程度、语气规则、对每个人的称呼。只注入本次请求实际出场的角色。
  卡里**不写**性格形容词和剧情背景——那会让模型为了"演得像"而加戏。
  称呼与自称来自人工整理的称呼表（20×20 矩阵，行=说话人、列=被称呼者、对角线=自称）：
  `python tools/build_character_cards.py --xlsx 称呼表.xlsx`。
  称呼表整张替换该角色的称呼，不与统计结果混合——卡是硬约束，来源必须干净。
  不带 `--xlsx` 时退回统计生成。语气规则（`speech`）任何情况下都需人工填写。
- **术语表** `tools/vendor/glossary.json` —— 只收录人工译文中有压倒性单一译法的词；
  译法随上下文变化的词（`ライブ` 演唱会/演出）不放进来，硬约束会逼模型译错。
  只注入原文中实际出现的词条。

### 分类型的剧情上下文

| 类型 | 规范路径 | 剧情上下文策略 |
|---|---|---|
| cidol P卡剧情 | `cidol-<角色>-3-<话>/` | **同组 01~03 合并成一次请求**，模型看到完整起承转合 |
| csprt S卡剧情 | `csprt-<批次>-<卡号>/` | **同组 01~03 合并成一次请求** |
| event 活动剧情 | `event/<号>/` | 顺序翻译 + 同组前文按原顺序全量注入；**翻译前先抽词生成本活动临时术语表** |
| dear 好感度剧情 | `dear/<角色>/<话>` | **滚动摘要 + 上一话全文**；自动机翻只写临时副本，正式摘要由重建任务维护 |
| pstory 培养故事 | `pstory/<卡>/<角色>/` | 严格整行精确复用；人工优先，机翻回退，同级多译法不复用 |
| pevent 培养事件 | `pevent/<号>/<角色>/<事件>/` | 严格整行精确复用；不注入剧情上下文 |
| other 其它剧情 | `live/` `unit/` `startup/` `tutorial/` … | 不注入剧情上下文 |

精确复用只对白名单中的 `pstory`/`pevent` 生效。匹配键包含剧情类型、行类型、说话人和完整原文，
包括标点、换行及占位符；不做 trim、模糊匹配或子串匹配。人工译文优先，没有人工译文时才使用已标明模型的机翻；
同一优先级有多个不同译法时安全跳过，交给模型重新判断。

参考行以 `REF|` 前缀、术语以 `TERM|` 前缀注入，即使模型误回显也不会被当成译文；
管线还会在还原阶段直接拒收含这些标记的译文。

### 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `TM_DIR` | `../csv_data`（相对 GakumasPreTranslation） | 翻译记忆目录，只读历史译文；精确复用按人工优先、机翻回退选择来源 |
| `TM_MAX_REF` | `40` | 参考行上限（event 的同组前文不受此限） |
| `MAX_LINES_PER_REQUEST` | `250` | 单次请求行数上限。合并后的同组 CSV 必须放得下，否则又被切开等于白合并 |
| `MAX_TOKENS` | 普通模型 `12288`；DeepSeek V4 Pro thinking `65536` | thinking 的推理与最终译文共用预算；管线会在付费请求前校验 |
| `DEAR_SUMMARY_FILE` | 不设 | dear 摘要路径；本地菜单指向 `tools/vendor/dear-summaries.json`，自动管线指向临时副本 |
| `DEAR_SUMMARY_WRITE` | 不设 | 只有自动管线临时副本设为 `1`；本地翻译不会回写正式摘要 |

对应的实现位于 `tools/vendor/`。运行 `python tools/sync_vendor.py`，或启动本地菜单/自动管线时，
会按 SHA-256 只同步内容变化的引擎文件到 `GakumasPreTranslation/src/`。
`dear-summaries.json` 是正式状态，不同步到上游 `src/`；自动机翻只写临时摘要副本。

`tools/vendor/build-dear-summaries.ts` 从 `proofread_csv > translated_csv > csv_data > ai_csv（需显式启用）`
选择来源，同话分段合并，按输入哈希复用未受影响的检查点，并在缺话、跳话或摘要回退时失败关闭。
`.github/workflows/update-dear-summaries.yml` 每 6 小时检查一次，也支持人工译文更新后的 repository dispatch。

自动管线采用付费防重策略：单个文件完全无有效输出时不原样重试，部分成功时只补发缺失行；
全局错误会停止剩余文件，并先把错误前已完成的剧情组播种到工作仓。若当前分支上一轮失败，
下一次定时首跑会在调用模型前暂停；手动 Re-run 或 `workflow_dispatch` 可明确恢复。

规范索引更新：运行 `python tools/update_story_index.py` 会从 gakuen-adapted-stories
拉取最新目录树并重新生成 `tools/vendor/story-index.json`，随后由管线覆盖到翻译引擎。

### csv_data 只放实装译文

`csv_data/` 是实装进游戏的翻译数据目录，**机翻产物一律不回写**，只推送到工作仓库
[gakumas-translation-work](https://github.com/chihya72/gakumas-translation-work) 供翻译者认领。
引擎升级后要把工作仓库里的旧机翻刷成新版，用
`python tools/seed_work_repo.py --refresh ...`——它以 issue 的 `tr::`/`pr::` 认领标记为闸门，
只覆盖无人认领的 `ai_csv/`，人工层 `translated_csv/`、`proofread_csv/` 任何情况下不碰。

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
