# AI 机翻流水线现状总结（2026-09-09）

> 写给「新开一个对话、没有任何上下文」的读者。目标是让读者不用再翻代码就能独立分析问题、提出方案。
> 所有数字、文件名、行为都来自 2026-09-09 当天对仓库、CI 日志、工作仓库的实际核对，不是推测。
> 涉及代码的地方给出文件路径，需要时再去看。

---

## 0. 一句话结论

- **慢**：CI 机翻一轮 39 个文件要 4～6 小时，原因只有一个——`MODEL` 是 DeepSeek V4 Flash，请求体不带 `thinking` 字段，而 DeepSeek V4 系列（Pro 与 Flash 都是）`thinking.type` 的**服务端默认值是 enabled**，不发字段不等于关，必须显式发 `{type: "disabled"}` 才关（这一点 2026-08-24 的提交 `2405fd72` 注释里写得很清楚，同日下一提交 `4cf8746b` 把这段开关整个删了）。于是每个请求思考 4.5 万～6.3 万 token，单次 5～10 分钟。换成 Flash 并没有变快，因为快慢取决于思考开没开，不取决于 Pro 还是 Flash。流程结构本身不慢，换成非推理模型同一轮预计 30～60 分钟。
- **不稳**：同一活动剧情里「進路」在三段被译成「未来去向 / 出路志愿 / 职业规划」。根因是术语没有进硬约束：术语表其实是人名表、event 抽词只看第一段且排除普通词、翻完没有校验。思考多少与一致性无关，重思考的模型照样不一致。
- **另一个真问题**：被取消/超时的 run 一个文件都不落盘，下一轮 cron 会把同一批全部重翻，钱白烧。今天就发生了：09:26 起跑、11:58 被手动取消，一个文件都没推到工作仓；14:37 cron 再起跑时去重台账没有任何变化，只能从头翻同一批。

---

## 1. 全局架构

### 1.1 仓库与职责

| 仓库 / 目录 | 角色 |
|---|---|
| `chihya72/Gakumas-Auto-Translate`（本仓库，master） | 流水线控制仓。`tools/auto_campus_pipeline.py` 是 CI 主脚本；`run.py` 是本地菜单；`tools/vendor/` 存自研的翻译引擎源码；`csv_data/` 是历史译文（3427 个 CSV），也是翻译记忆（TM）的数据源；`name_dictionary.json` 是人名/术语表 |
| `GakumasPreTranslation/`（本仓库内目录，**被 .gitignore 忽略**） | 上游 `imas-tools/GakumasPreTranslation` 的克隆。真正跑翻译的 TypeScript 引擎。CI 每次临时 clone，然后用 `tools/vendor/` 的文件**覆盖**其 `src/`。本地也是同一套覆盖机制（`python tools/sync_vendor.py`） |
| `DreamGallery/Campus-adv-txts` | 只读上游。`Resource/*.txt` 是游戏原文，当前 3870 个 |
| `chihya72/gakumas-translation-work` | 协作工作仓。目录 `raw_txt/ ai_csv/ translated_csv/ proofread_csv/ records/`，加 GitHub Issues 作认领台账。CI 机翻结果推到这里 |
| `chihya72/gakumas-viewer`（GitHub Pages） | 网页工作台，成员在线翻译/校对，直推工作仓 |
| `chihya72/gakuen-adapted-translation-data-pm` | 最终成品 CSV 仓，只收本地菜单校验后手动同步的文件 |

### 1.2 数据流（CI 一轮）

```
Campus Resource/*.txt
  │ 1. 列出 Campus 全部 txt，减去「已知文件」（本仓 data/ csv_data/ + 工作仓 issue 标题 + 工作仓各目录文件）
  │ 2. 前缀白名单过滤（adv_cidol, adv_csprt, adv_dear, adv_event, …），limit 默认 50
  │ 3. 下载新增 txt，无台词的空剧本直接跳过
  │ 4. preprocessor.preprocess_txt_files(preserve_html=True) → todo/untranslated/csv_orig + csv_dict
  │ 5. HTML 标签掩码为 GAT_TAG_n（csv_dict 的 text 列）
  │ 6. cidol / csprt 同组 01~03 合并成一个 CSV（merge_groups），其余原样
  │ 7. clone GakumasPreTranslation，yarn install，vendor 覆盖 src/，写 .env
  │ 8. yarn translate:folder（引擎，逐文件串行）
  │ 9. restore_csvs：拆回分段、还原原文与标签、校验行数/标签/回显 → todo/translated/csv
  │10. 校验失败的文件删掉输出重翻，最多 3 轮；仍失败则在工作仓开「机翻异常」issue
  │11. seed_work_repo.py：CSV 推 ai_csv/、原文推 raw_txt/、每文件开一个 issue
  ▼
gakumas-translation-work（网页工作台接手）
```

关键性质：**第 9～11 步只在第 8 步整体结束后才执行**。第 8 步中途被取消、超时、抛错（fail-fast），已翻好的文件留在 runner 的 `tmp/translated/`，随 runner 销毁。代码里对「引擎抛错」有兜底（先保存再失败），但对「job 被取消 / 6 小时上限」没有任何兜底。

### 1.3 触发方式

`.github/workflows/campus-to-work.yml`：
- cron `17 0-15 * * *`（北京时间 08:17～23:17 每小时）+ 手动 `workflow_dispatch`（可填 prefix / limit）
- `concurrency: campus-pipeline, cancel-in-progress: false` → 后到的 run 排队等，不并发
- Secrets：`PIPELINE_PAT`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL`（用户确认为 `deepseek-v4-flash`，2026-08-24 01:44 UTC 更新，即提交 `4cf8746b` 删掉 thinking 开关后 3 分钟；日志里值被遮蔽。本地 `.env` 仍是 `deepseek-v4-pro`，workflow 注释里的「V4 Pro」已过时）、`MAX_TOKENS`（2026-08-16 更新，实际值 65536，日志里 completion_tokens 顶到 65533 可证）
- 无新增文件时一轮 30 秒结束。最近 30 天真正翻过东西的 run：08-25（11 min）、08-26（3 min）、09-03（27 min 失败 / 39 min 成功 / 8 min 成功）、09-09（两个 run 分别 152 min、131 min 后被手动取消；第三个 14:37 UTC 起跑，80 min 后因 API 返回空正文而 fail-fast，保存了 16 个文件）

另一个 workflow `.github/workflows/update-dear-summaries.yml`：每 6 小时用工作仓人工层重建 dear 滚动摘要，写回 `tools/vendor/dear-summaries.json` 并提交。近期每次 30～40 秒（无变化），运行正常。

---

## 2. 翻译引擎详解（`tools/vendor/*.ts` → `GakumasPreTranslation/src/`）

### 2.1 文件与同步

`gakumas_auto_translate/modules/vendor_sync.py` 按 SHA-256 把以下文件复制到 `GakumasPreTranslation/src/`：
`tm.ts`、`translate.ts`、`prompts.ts`、`story-index.json`、`character-cards.json`、`build-dear-summaries.ts`，
以及 **`name_dictionary.json` → 改名为 `glossary.json`**（这一点很重要，见 4.2）。
入口脚本 `tools/vendor/translate-folder.ts` 单独覆盖到 `scripts/translate.ts`（改为 fail-fast）。
`dear-summaries.json` 是运行时状态，不复制进 src，通过环境变量 `DEAR_SUMMARY_FILE` 指路径。

### 2.2 一次请求怎么构成（`translate.ts` → `chat()`）

请求体**只有** `{ model, messages, max_tokens }`。这是 2026-08-24 提交 `4cf8746b` 的明确决定：删掉了此前按模型名分支塞 `thinking` / `reasoning_effort` 的逻辑，理由是「每换一家 API 就要再写一套判断」。温度、推理强度全部用服务端默认。超时 `API_TIMEOUT_MS` 默认 600 秒。

`messages` 结构：
1. system：`chinesePrompt`（`prompts.ts`），规定输入/输出格式、三条「最高禁令」（禁「酱」、禁「呐」、句首「嘛」）、约束优先级：术语表 > dear 已固定称呼 > 角色卡 > REF 参考行 > 模型自己判断
2. 若干 user 消息，每个是一个「上下文块」（只注入非空的）：
   - **术语表块**：`glossaryBlock()` —— 只注入原文中实际出现的词条，格式 `TERM|日文|中文`
   - **剧情摘要块**（仅 dear）：`summaryBlock()` —— 该角色的滚动摘要 + 分段剧情线 + 已固定称呼
   - **角色卡块**：`characterCardBlock()` —— 只注入本批出场的角色，自称/敬语/语气/称呼
   - **参考行块**（仅 event）：`referenceBlock()` —— 同一活动此前各段的全部译文，`REF|i|name|原文|译文`
   - event 类型把参考行放最前面，其余类型放最后（为吃前缀缓存）
3. 最后一个 user 消息：待翻译行，`index|name|text`，`\n` 换成 `<br>`

输出解析（`DialogueListDeser.deserialize`）：**按模型带回的行号归位**，不按输出顺序；同行号多次取最后一次；行数不够只重试缺失行（最多 2 次），一行都没有则直接抛错不重试。`finish_reason=length` 时保留已有行只补缺失行。

### 2.3 分类型策略矩阵（`tm.ts` `STORY_POLICIES`）

| 类型 | context | prefill | 实际行为 |
|---|---|---|---|
| cidol | group-merge | none | 管线侧把 01~03 合并成一个 CSV，一次请求翻完，引擎不注入 REF |
| csprt | group-merge | none | 同上 |
| event | sequential | none | 每段一个文件按序翻；前面各段译文全量作为 REF 注入；翻第一段前先调一次 API 抽「活动临时术语表」 |
| dear | summary | none | 注入该角色的滚动摘要；翻完一话再调一次 API 更新摘要 |
| pstory / pevent | none | exact-row | 不注入剧情上下文；整行原文（含类型、行类型、说话人）与 TM 精确匹配时直接复用，人工优先于机翻，同层歧义不命中 |
| 其他 | none | none | 只有术语表 + 角色卡 |

分类来源：`story-index.json`（3776 条，由 `tools/update_story_index.py` 从规范仓库目录树生成，**最后更新 2026-08-06**）。索引没有的文件名走正则兜底 `parseStory()`。

同一文件超过 `MAX_LINES_PER_REQUEST`（默认 250）行才会分批；分批时前批译文自动作为后批前文（自我喂食进 TM，只在内存里）。

### 2.4 翻译记忆 TM（`tm.ts` `TranslationMemory`）

- 数据源：`TM_DIR`，CI 设为本仓 `csv_data/`（3427 文件，加载 99690 对）
- 用每个 CSV 末尾「译者」行区分人工/机翻（正则匹配 gpt/deepseek/claude/… 即机翻）
- 只有 pstory/pevent 做精确复用；event 用作 REF；其他类型不用
- **实际构成**：`csv_data` 的译者分布 —— gpt-4o 1123、deepseek-chat 1045、DeepSeek-V3 200、deepseek-reasoner 189、deepseek-v4-pro 83、pm 190、煉金術式 105、病毒 99 …… 也就是**绝大多数是历史机翻**，人工层很薄
- 机翻结果不回写 `csv_data`（2026-08-08 起），避免自我污染

### 2.5 术语表（`glossary.json` = `name_dictionary.json`）

- 262 条。其中 **140 条的键是 csv_data 里出现过的说话人名**（如「ゲーセンのおじさんA」「初星学園の生徒B」），其余是人名全称/昵称（藤田ことね、りんちゃん、Pっち）、学园名、歌曲名（キミとセミブルー、一番星）
- **没有任何游戏世界通用名词**：進路、研修生、練習生、レッスン、事務所、ボイトレ 等都不在
- 注入规则：`activeGlossary()` 只挑原文里子串出现的条目；event 临时表与全局表合并，冲突时全局表优先
- prompt 里写它是「硬约束」，但**翻完没有任何代码检查术语是否真被遵守**。唯一用到 `exactReuseAllowed()` 校验术语的是 pstory/pevent 的精确复用路径

### 2.6 角色卡（`character-cards.json`）

16 个角色：美鈴、佑芽、咲季、手毬、清夏、広、星南、リーリヤ、千奈、麻央、莉波、燕、ことね、燐羽、四音、あさり先生。由 `tools/build_character_cards.py` 从 csv_data 统计自称/称呼生成草稿，语气规则人工填写。只注入本批出场角色。

### 2.7 dear 滚动摘要（`tools/vendor/dear-summaries.json`）

- 按角色码存：`through_episode`、`summary`（200～500 字）、`fixed`（已固定称呼）、`checkpoints`（分段剧情线）
- 当前进度：amao/hmsz/hrnm/hski/hume/kcna/kllj/shro/ssmk/ttmr 到第 37 话；atbm/fktn/jsna 到第 27 话
- 翻第 N 话时校验 `through_episode === N-1`，否则**拒绝注入**并打 WARN；翻完后 `updateDearSummary()` 再调一次 API 生成新摘要，同样校验连续性，不连续则拒绝回写
- CI 里写的是 runner 临时副本（`dear-summaries.runtime.json`），**翻完即丢**；正式文件只由 `update-dear-summaries.yml` 从工作仓人工层重建。设计意图：机翻状态不污染正式摘要
- 每个 dear 文件因此是 **2 次 API 调用**（翻译 + 摘要）

### 2.8 event 临时术语表（`translate.ts` `buildEventGlossary()`）

- 翻 event 第一段前调一次 API，让模型从**当前文件**的台词里抽最多 30 条专有名词
- 结果按活动 group 缓存，**02～05 段直接复用第一段的抽词结果**，不再抽
- `eventGlossaryPrompt` 明令「仅收录活动名、场地名、活动内设定和限定称谓；不要收录普通词、人名或语气词」

---

## 3. 本地流程（`run.py`）与「线上线下同构」原则

菜单：1 检查新增 → 2 预处理（人名替换，用 name_dictionary）→ 3 翻译（把 csv_dict 复制到引擎 tmp/untranslated，提示手动 `yarn translate:folder`）→ 4 合并生成 txt（纯中文/双语）→ 5 清理归档 → 6 切换模式 → 9 配置。

本地引擎 `.env`（不入库）：`MODEL=deepseek-v4-pro`、`MAX_TOKENS=65536`、`DEAR_SUMMARY_FILE` 指向正式摘要（只读，本地不回写）。本地菜单 3 **不合并同组 CSV**（与 CI 不同），逐文件复制。

用户反复强调的原则：**云端流程必须与本地 run.py 同构，不引入本地没有的机制**（例如曾提出的状态文件方案被否决）。提方案时要检查是否违反这一点。

---

## 4. 今天（2026-09-09）发生了什么

### 4.1 时间线（UTC）

| 时间 | 事件 |
|---|---|
| 09:26 | cron run `34334719661` 起跑。Campus 3870 个 txt，已知 3445，新增 50，limit 50 全取；合并/跳空后 39 个 CSV 待翻 |
| 09:27～11:56 | 串行翻了 22 个文件（详见 4.2） |
| 09:47 | 下一班 cron run `34336685828` 起跑，被 concurrency 排队 |
| 11:58 | 两个 run 都被手动取消。**22 个已翻文件全部丢失**（未到 restore/seed 步骤） |
| 14:37 | cron run `34364795880` 起跑。早上的 run 没有推任何文件到工作仓，去重台账不变，新增列表与早上完全相同（同样 39 个 CSV），**从头重翻同一批** |
| 14:39～15:52 | 重翻了 12 个文件，顺序与早上一致。前缀缓存这次命中很高（cidol 5504/5600），因为输入与早上逐字节相同 |
| 15:57 | 翻 `adv_dear_fktn_037-01` 时 API 返回 **content 为空、finish_reason=stop、reasoning 96917 字符**——模型把全部输出写进了思考、正文一个字没给。引擎抛错 fail-fast，管线走「引擎抛错先保存」兜底：restore + seed 了 4 个剧情组共 16 个文件（工作仓 issue #404～#419：cidol-jsna-3-017 ×3、csprt-3-0099 ×3、dear_amao_037-01、dear_fktn_028～036），run 以 failure 结束 |
| 09-10 | 无进行中/排队的 run。剩余约 23 个文件（fktn_037-01、fktn_037、hmsz/hrnm/hski/hume_037-01、jsna_028～037 等）会在下一班 cron 被当作新增继续翻，模型不变则同样每个 5～10 分钟 |

### 4.2 逐文件耗时（第一个 run）

| 文件 | 耗时 | 备注 |
|---|---|---|
| adv_cidol-jsna-3-017（01~03 合并） | 6.5 min | 1 次请求，reasoning 45.5k tok |
| adv_csprt-3-0099（合并） | 6.7 min | reasoning 48.9k |
| adv_dear_amao_037-01 | 4.0 min | 摘要「已到 37 话、当前 37 话」→ 拒绝注入、拒绝回写 |
| adv_dear_fktn_028～036（9 个） | 7～11 min 各 | 每个 2 次请求；摘要链 27→36 正常推进 |
| adv_dear_fktn_032 | 10 min | 翻译请求 **finish_reason=length**：completion 65533，reasoning 63.5k，正文缺 4/104 行 → 补翻成功 |
| adv_dear_fktn_037-01 | 7 min | **排序在 fktn_037 之前**（`-` < `.`），摘要链被它推到 37 |
| adv_dear_fktn_037 | 6 min | 真正的第 37 话，反而被判「非连续」→ 无摘要、不回写 |
| adv_dear_hmsz/hrnm/hski/hume_037-01 | 3～4.5 min 各 | 同 amao_037-01，全部拒绝注入摘要 |
| adv_dear_jsna_028～030 | 8～9 min 各 | 正常 |
| adv_dear_jsna_031 | — | 取消时正在跑 |

22 个文件 149 分钟，平均 6.8 分钟/文件。按这个速度 39 个文件约 4.4 小时，加上摘要请求接近 GitHub Actions 6 小时上限。

### 4.3 token 侧的事实

- 翻译请求：prompt 1.8k～8k；reasoning 8.7k～63.5k；正文 500～5000 字符
- 摘要请求：prompt 3.6k～5k；reasoning 5k～18k
- 前缀缓存命中普遍很低（0 或 1152/256），因为每个文件上下文块都不同
- MAX_TOKENS=65536 中绝大部分被思考吃掉，fktn_032 那次正文只剩 2000 token 就被截断

### 4.4 「-01」文件是什么

Campus 新出现 22 个 `adv_dear_<角色>_010-01.txt` / `037-01.txt`。核对 amao/fktn 的 037 与 037-01：**内容不同**，037-01 只有 23 行，是同一话的追加短篇（不是重复文件）。当前系统对它的处理：
- `story-index.json`（08-06）里没有它 → 走正则兜底，`(?:[-_]\d+)?` 吞掉后缀，判为**第 37 话**
- 文件名排序 `037-01.csv` < `037.csv`，先翻追加篇再翻主篇
- 摘要逻辑把它当作第 37 话本身：主篇已在摘要里 → 追加篇「非连续」；若主篇还没翻（fktn），追加篇先把链推到 37，主篇反被拒
- 去重按文件名精确匹配，037-01 与 037 是两个文件，所以它们是**合法新增**，不是重复翻译

---

## 5. 术语不一致的实证（event_028）

工作仓 `ai_csv/adv/event/028/main-01~05.csv`（人工层已完成，机翻稿仍在）。原文含「進路」6 行：

| 段 | 原文 | 机翻 |
|---|---|---|
| 01 | 進路希望調査票 | 未来去向调查表 |
| 02 | 進路希望 / 進路の調査票 | 出路志愿 / 出路调查表 |
| 03 | 進路指導の先生 | 职业规划老师 |

三段三个译法。每段都注入了前面各段的全部 REF，也都用了重思考模型，说明「软参考 + 多思考」不能保证一致，只有硬约束 + 校验能。

---

## 6. 问题清单（按根因归并）

### P1 速度：推理模型放开想
- 事实：`MODEL` 为 DeepSeek V4 Flash；请求不带 `thinking` 字段；DeepSeek V4 系列服务端默认 `thinking.type=enabled`，只有显式发 disabled 才关；每请求思考 4.5～6.3 万 token
- 历史：08-16 提交 `8247447f` 和 08-24 提交 `2405fd72` 曾按模型名/任务显式发 `thinking: {type: enabled|disabled}`；同日 `4cf8746b` 以「不按模型名分支」为由全部删除，从此完全依赖服务端默认。当天 MODEL 换成 Flash，但默认思考没有随之关掉
- 影响：单文件 5～10 分钟；一轮 4～6 小时；触 6 小时上限；思考挤占 MAX_TOKENS 导致正文截断（fktn_032 早上那次）；还出现过**思考 9.7 万字符后正文为空**（fktn_037-01，14:37 那轮），直接让整轮 fail-fast
- 波动很大：同一个 fktn_035，早上思考 5.4 万 token，下午第一次请求只思考了 27 个字符、13 秒返回。快慢完全由模型当次思考量决定，不是流程或网络
- 与既有决定的关系：2026-08-24 决定「只发标准字段、不按模型名分支」。`reasoning_effort` 是 OpenAI 标准字段，但传它与「用服务端默认」有张力，需用户拍板

### P2 术语不一致：术语没进硬约束
- P2a `glossary.json` 实为人名表（262 条，140 条是说话人名），无游戏通用名词
- P2b event 抽词只用第一段文本，且 prompt 排除「普通词」；02～05 段新出现的词永远进不了表
- P2c 翻完无校验：术语表被标「硬约束」但没有代码检查；`exactReuseAllowed()` 里有现成的「原文含 A 日文 → 译文须含 A 中文」检查，只用于精确复用
- P2d temperature 用服务端默认（通常 1.0），增加随机性；同属「标准字段」决策范围

### P3 dear 「-01」追加篇处理错误
- 被当作同一话；排序在主篇之前；导致主篇拒绝注入摘要、摘要链被短篇推进
- `story-index.json` 一个多月没刷新，所有新文件都走正则兜底
- 涉及 `tm.ts parseStory()`、`build-dear-summaries.ts NAME_RE`（它已经把 `-01` 视为同话分段并合并，思路与翻译侧不一致）

### P4 成果不落盘：取消/超时 = 全丢 = 下轮重烧
- `restore_csvs` + `seed` 在整批翻译结束后才跑；引擎抛错有兜底，job 取消/超时没有
- 今天实际损失：22 个文件、约 2.5 小时 API 消耗；14:37 的 run 正在重复同一批
- 已知约束：不能引入本地没有的状态文件机制（用户原则）。但 `translate-folder.ts` 本来就 `skipExisted`，`tmp/translated/` 天然就是断点，只是随 runner 消失
- 对照：14:37 那轮是「引擎抛错」而不是「取消」，现有兜底生效，16 个文件保住了。说明兜底逻辑本身没问题，缺的只是对取消/超时这两种退出方式的覆盖

### P5 其他观察（非紧急）
- TM 人工层薄：csv_data 绝大多数是历史机翻，「人工优先」实际很少命中
- 前缀缓存基本吃不到；event 把 REF 放前面的优化收益有限
- 每个 dear 文件 2 次调用，摘要调用同样在重思考，本身占一轮 20～30% 时间
- 上游 `index.json`（2762 条）用 info 行的 jsonUrl 去重，与本仓去重是两套，目前未见冲突
- `character-cards.json` 08-08 后未更新；新角色（如 四音 之外的新增）出场不会有卡

---

## 7. 候选方案（供新对话独立评估，本文不定案）

| # | 方案 | 改动点 | 规模 | 解决 | 风险 / 与既有原则的关系 |
|---|---|---|---|---|---|
| A | 换 `MODEL` secret 为**不带默认思考**的模型（如 deepseek-chat 这类非 V4 型号，或其他厂商的非推理模型） | GitHub Secrets | 0 代码 | P1 | 已换成 Flash 无效，因为 Flash 也默认思考；译文风格可能变，需要一轮对比 |
| B | 请求体固定加 `thinking: {type: "disabled"}`，或由可选环境变量 `THINKING=off` 控制 | `translate.ts chat()` | ~3 行 | P1 | `thinking` 是 DeepSeek 专有字段，不是 OpenAI 标准字段；其他厂商可能忽略或报错，与「只发标准字段」原则直接冲突，需用户拍板。可选变量形式不设时行为不变 |
| C | event 抽词按组累积：每段都抽、合并进缓存；prompt 纳入「反复出现的设定名词」 | `translate.ts buildEventGlossary()`、`prompts.ts` | ~10 行 | P2b | 每段多一次抽词调用（非推理模型下几秒） |
| D | 术语事后校验：翻完检查术语表命中的行，不合格的走现有「只重试缺失行」路径 | `translate.ts translateCsvTextInfo()`，复用 `exactReuseAllowed()` 的判断 | ~20 行 | P2c，兼顾跨段一致 | 极端情况下反复重试；需上限 |
| E | 补全局术语表：脚本从 csv_data 统计高频日文名词及其多数译法 → 人工审 → 进 `name_dictionary.json` | 新脚本 `tools/`，`name_dictionary.json` | 一次性脚本 + 人工审词 | P2a，覆盖全部类型 | 人工审词耗时；name_dictionary 同时被本地菜单 2 用作人名替换，加非人名词条要确认 preprocessor 只替换 name 列 |
| F | dear 追加篇：`-01` 视为同话「分段」而非同话本身（与 build-dear-summaries 一致）；排序把主篇放前 | `tm.ts parseStory()/classifyCanonical()`、`translate-folder.ts` 排序 或 管线侧 | ~15 行 | P3 | 需定义追加篇的摘要语义（是否并入 37 话摘要） |
| G | 刷新 `story-index.json`（`tools/update_story_index.py`）并纳入 CI | vendor 数据 | 0 代码 | P3 部分 | 规范仓库是否已有 -01 文件未核实 |
| H | **已实施（2026-09-10 提交 `bc895760`）**：`translate_streaming` 逐行读引擎日志，见「Output to」即对该文件 restore + seed；`restore_csvs` 加 `only` 参数 | `auto_campus_pipeline.py` | ~60 行 | P4 | seed 对已推文件/已开 issue 幂等；推送失败不打断引擎、下次一起重推。一轮多出最多 39 次 seed，每次几十秒 |
| I | 给 job 加 `timeout-minutes` 并在超时前主动收尾（trap） | workflow | 小 | P4 | GitHub 取消信号能否被 Python 捕获需验证 |
| J | 翻译与摘要用不同模型（摘要用便宜/非推理） | 引擎需第二组配置 | 中 | P1 部分 | 增加配置面，与「不按模型分支」原则可能冲突 |

建议阅读顺序：先 A（零代码、立刻见效、验证「慢=模型」的判断），再 C+D 一起（一个让术语进表，一个保证表被遵守），F/G 修 dear 追加篇，H 止住重烧。E 收益最大但人工成本最高，放最后。

---

## 8. 用户已明确的决策与偏好（提方案前必读）

1. **请求体只发 OpenAI 兼容标准字段**，推理强度、温度用服务端默认，不按模型名分支（提交 `4cf8746b`）
2. **云端流程与本地 run.py 同构**，不引入本地没有的机制（状态文件方案曾被否决）
3. **线上纯中文保留 ruby/HTML 标签、线下双语删标签**，是故意的两套，不要统一
4. **机翻不回写 csv_data**；`csv_data` 是人翻底稿正源
5. **dear 正式摘要只由人工层重建**，机翻只用临时副本
6. 逐条方案回复时，**只有写「改」的那条是执行指令**，其余是讨论
7. 网页端不做入库；成品走本地菜单手动同步 data-pm

---

## 9. 快速核对命令

```bash
# 最近的流水线 run（看耗时与结论）
gh run list --workflow campus-to-work.yml --limit 15

# 某个 run 的引擎日志（替换 JOB_ID：gh api repos/chihya72/Gakumas-Auto-Translate/actions/runs/RUN_ID/jobs）
gh api repos/chihya72/Gakumas-Auto-Translate/actions/jobs/JOB_ID/logs | grep -E "Translating|API response|Output to|ERROR|WARN"

# 干跑看下一轮会翻哪些文件（本地需 gh 登录）
python tools/auto_campus_pipeline.py --dry-run --prefix adv_cidol,adv_csprt,adv_dear,adv_event,adv_live,adv_pevent,adv_pgrowth,adv_presult,adv_produce-refresh,adv_pstory,adv_startup,adv_tower,adv_tutorial,adv_unit --limit 50

# 工作仓的机翻稿（按规范路径）
gh api -H "Accept: application/vnd.github.raw" repos/chihya72/gakumas-translation-work/contents/ai_csv/adv/event/028/main-01.csv

# 术语表构成
python -c "import json;g=json.load(open('name_dictionary.json',encoding='utf8'));print(len(g))"

# Campus 里的 -01 追加篇
gh api "repos/DreamGallery/Campus-adv-txts/git/trees/main?recursive=1" --jq '.tree[].path' | grep -E "adv_dear_[a-z]+_[0-9]+-0[0-9]\.txt"
```

---

## 10. 关键文件索引

| 路径 | 作用 |
|---|---|
| `.github/workflows/campus-to-work.yml` | CI 主流程触发与环境 |
| `.github/workflows/update-dear-summaries.yml` | dear 正式摘要重建 |
| `tools/auto_campus_pipeline.py` | CI 主脚本：去重、下载、预处理、掩码、合并、调引擎、校验、重试、seed |
| `tools/seed_work_repo.py` | 推工作仓 + 开 issue |
| `tools/vendor/translate.ts` | 引擎核心：请求构造、行号归位、缺行重试、event 抽词、dear 摘要更新 |
| `tools/vendor/tm.ts` | 策略矩阵、分类、TM、术语表/角色卡/摘要块生成、精确复用校验 |
| `tools/vendor/prompts.ts` | 三个 system prompt（翻译 / event 抽词 / dear 摘要） |
| `tools/vendor/translate-folder.ts` | 引擎入口，逐文件串行，fail-fast |
| `tools/vendor/build-dear-summaries.ts` | 从人工层重建 dear 摘要 |
| `tools/vendor/story-index.json` | 剧情分类索引（08-06） |
| `tools/vendor/character-cards.json` | 16 角色卡 |
| `tools/vendor/dear-summaries.json` | dear 滚动摘要正式文件 |
| `name_dictionary.json` | 人名/术语表（同步为引擎的 glossary.json） |
| `gakumas_auto_translate/modules/vendor_sync.py` | vendor → 引擎 src 同步规则 |
| `gakumas_auto_translate/modules/utils.py` | merge_groups / split_merged |
| `gakumas_auto_translate/modules/preprocessor.py` | txt → CSV 预处理，人名替换 |
| `csv_data/` | 3427 个历史 CSV，TM 数据源 |
| `ROADMAP.md` | 在线协作项目路线图与已完成项 |

---

## 11. 工作仓当前状态（2026-09-09）

- Issues：closed 345、open 37。open 里 31 个是「翻译完成、校对进行中」，6 个 dear 文件两轨都完成但标签仍是「待翻译」（标签未同步，不影响流程）
- 目录文件数：`ai_csv` 约 200（人工完成后有清理）、`translated_csv` 422、`proofread_csv` 387、`records` 381
- `records/*.json` 记录每文件的翻译/校对操作者、revision、状态，是网页端的真相源

---

## 12. 附：今日日志中值得记住的几行

```
INFO: TM loaded: 99690 pairs from 3427 files
INFO: API response: finish_reason=stop, content_chars=5113, reasoning_chars=117641, prompt_tokens=5600, completion_tokens=48680, reasoning_tokens=45542
WARN: dear 摘要覆盖到第 37 话，但当前是第 37 话——拒绝注入非连续摘要
WARN: API 输出被 max_tokens 截断；将保留已返回的有效行，并且只重试缺失行。
INFO: API response: finish_reason=length, ... completion_tokens=65533, reasoning_tokens=63534
ERROR: 缺 4/104 行译文，行号: 100, 101, 102, 103
INFO: 仅重试缺失的 4 行；已成功的 100 行不会重发
WARN: dear 固定译法 ことね 与术语表冲突，按优先级采用术语表
##[error]The operation was canceled.
```

---

## 13. 2026-09-10 复查：H 落地后的剩余缺陷

H（翻一个推一个）已上线并实测生效：run `34378843954` 从 16:46 UTC 起每翻完一个文件就出一个 issue（#420～#430）。以下按影响排序。

### 13.1 毒文件会卡死队列（新发现，最高）—— **已修，见 13.9**
- `tools/vendor/translate-folder.ts` 对**任何**单文件异常都 `throw` 终止整轮，不区分引擎已经分好的 `FatalApiError`（4xx 认证/余额/参数）和普通错误（正文为空、缺行重试用尽）
- 文件按名字排序，稳定不变。一个文件若每次都让模型返回空正文，它永远排在剩余队列最前，每小时一班 cron 都在它身上失败，后面的文件永远翻不到
- 它不是校验失败，`mark_failed` 不会给它开「机翻异常」issue，去重台账也不会记住它——没有任何人能看到队列卡住了
- 09-09 15:57 的 `fktn_037-01` 空正文是偶发（今天同文件成功），但机制上就是这个形状
- 修法：入口脚本只对 `FatalTranslationError` 中止，其它异常打日志跳过继续；管线在引擎退出后把「没有输出」的文件计入 failures，走现有 3 轮重翻 → `mark_failed`。约 10 行

### 13.2 dear 摘要机制在 CI 里近乎失效（结构性）
- 正式摘要只随人工层推进（fktn/jsna 停在 27）；CI 用临时副本，翻完即丢
- 于是每一轮都从正式摘要起算：本轮 `jsna_028` 有摘要（27→28），但 `jsna_031` 校验失败被跳过后，`032`/`033` 与临时摘要（到 30）不连续 → 拒绝注入。实证：工作仓 jsna 目录有 028/029/030/032/033，缺 031
- 前一轮翻完的 `fktn_028～036` 摘要随 runner 消失，本轮 `fktn_037` 起算点仍是 27 → 也没摘要
- 结论：只有「同一角色整条链在同一轮内无一失败地翻完」摘要才起作用；现实中几乎不成立
- 可选方向：临时摘要跨轮持久化（但用户原则是机翻状态不写正式文件，需另开文件或接受现状）；或接受 dear 靠角色卡+术语表

### 13.3 dear 追加篇 `-01` 被当作同一话本身（沿 P3）—— **已修，见 13.10**
- 规范仓库 `imas-tools/gakuen-adapted-stories` 已收录 `dear/amao/037-01.csv`、`dear/fktn/037-01.csv`，但 `classifyCanonical()` 与 `parseStory()` 都取前导数字 → 第 37 话，刷新 story-index 不解决
- 排序 `037-01` < `037`，追加篇先翻、把链推到 37，主篇反被拒
- `build-dear-summaries.ts` 已把 `-01` 当第 37 话的分段合并；翻译侧应对齐：`-01` 视为「第 37 话第二段」——注入条件放宽为 through ∈ {N-1, N}、不回写；排序主篇在前

### 13.4 H 引入的回归：合并组部分推送（中）
- 合并翻的 cidol/csprt 组里一段校验失败时，其它段已被 harvest 推走；第二轮整组重翻后，seed 的「已存在不覆盖」让旧段留下，新段补入 → 同组来自两次请求
- 行对齐不受影响（每段独立还原），只是组内风格/术语可能不一致，违背「整组回炉」的本意
- 修法：harvest 里排除本轮 failures 所在组的文件。约 3 行

### 13.5 沿用未决：思考开着（P1）
- 本轮实测每文件 4～9 分钟；50 个文件预计 4～5 小时。两条路仍等拍板：请求体加 `thinking: {type: "disabled"}`（DeepSeek 专有字段），或换非 V4 模型

### 13.6 沿用未决：术语一致性（P2a/b/c）
- 无变化。event 抽词只看第一段、术语表实为人名表、无事后校验

### 13.7 潜在项（现在不出事）
- `known_files` / `existing_issue_titles` 用 `gh issue list --limit 1000`，工作仓现 408 个 issue，超过后去重静默截断 → 重复翻+重复开 issue。gh 本身支持更大 limit，到时改数字即可
- 上游 `GakumasPreTranslation/index.json`（2479 条）里的 jsonUrl 会被入口脚本静默跳过且不输出；当前批次无一命中，但一旦命中就是「每小时被当新增、永远不产出、无报错」
- 本地 `.env` 仍是 `deepseek-v4-pro`，CI 是 flash，两边译者标签不同；workflow 注释仍写「V4 Pro」

### 13.8 run `34378843954` 的结局（09-09 19:09 UTC）与新证据 —— 可观测性缺口**已修，见 13.9**
- 结果：推送 14 个剧情组后，在 `adv_pstory_003_fktn_selection-failure-01` 上 fail-fast 退出。该文件 API 正常返回（content 1308 字符、思考 2206 字符、15 秒），但**解析出 0/11 个有效行**——模型给了译文却不是 `index|name|text` 格式。这个文件将是下一轮队首，若再次 0 行即 13.1 所述的卡死
- 4 个 dear jsna 文件（031/035/036/037-01）**连续 3 轮**在同样的行上把全部 `GAT_TAG_n` 占位符丢掉（`trans=[]`），已开「机翻异常」issue #444～#447。同一轮里 jsna 028～034 共 30 个带标签行全部保留；fktn_036 里同构的 `『<r\=プリマステラ>一番星</r>』` 也保留了。本地重放预处理+掩码，失败文件的引擎输入与通过文件看不出结构差异（保标签模式下不做人名替换）。3 轮独立请求结果一致，说明是模型对这几个文件的稳定倾向，不是随机抖动，但触发因素无法从现有信息判断
- **根因层面的缺陷：看不见模型原始输出**。`chat()` 只在 debug 级打 Generated Text，CI 是 info；校验失败信息只打标签签名不打译文；`requeue_failures` 直接删掉失败输出。三者叠加，事后无法诊断任何一类模型输出问题。修法：0 有效行时把原始 content 前几百字符打到 error；`validate_rows_html_tags` 的报错附上 trans 前 80 字符；失败文件搬到 `tmp/failed/` 而不是删除（或至少 print 整行）

### 13.9 2026-09-10 第二批改动（提交在 `bc895760` 之后）
- 毒文件跳过：`translate-folder.ts` 只对 `FatalTranslationError` 中止，单文件错误跳过；连续 3 个失败视为全局故障停下。管线 `missing_outputs()` 把引擎正常退出后没输出的文件按组计入失败 → 3 轮重翻 → 机翻异常
- 重跑选项：workflow 输入 `retry_failed`（`all` 或 `YYYY-MM-DD`）；管线 `failed_issues()` 读 open「机翻异常」issue 为待翻列表，无则直接结束；成功后 `gh issue edit` 原地改回正常认领 issue
- 留原始输出：0 有效行时 error 级打模型正文前 800 字符；标签校验报错附整行译文
- ruby 读音词条：`name_dictionary.json` 新增 `<r\=プリマステラ>一番星</r>`→`<r\=Prima Stella>启明星</r>`、`<r\=セレクション>選抜試験</r>`→`<r\=Selection>选拔考试</r>`、`選抜試験`→`选拔考试`。实现：`RUBY_TAG_MAP` 在 unmask 时替换开标签，校验期望值同步替换。用户确认 `-01` 是补充话（游戏内 10.5 / 37.5 话），13.3 的修法方向不变，尚未实施

### 13.10 dear 补充篇实施（2026-09-10）
- 用户确认 `-01` 是游戏内 10.5 / 37.5 话的补充剧情。`classifyStory` 统一打 `supplement` 标记（不依赖索引）；`summaryBlock` 对补充篇要求摘要已到 N；`updateDearSummary` 补充篇回写后 through 仍为 N；入口排序主篇在补充篇前
- ts-node 实测：amao 摘要到 37 → 037 拒绝、037-01 注入、038 注入、038-01 拒绝；排序 036 < 037 < 037-01
