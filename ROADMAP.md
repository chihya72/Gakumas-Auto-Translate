# 在线协作翻译工作流 — 项目进度表

> 目标：把现有"工作群传文件"的多人翻译协作，搬到自建 gakumas-viewer 上，实现认领制在线翻译/校对。
> 最终产物分两套：A. 纯中文 TXT 用来录屏，线上完成；线上中间 CSV（AI机翻版、人工翻译版、人工校对版）和最终录屏 TXT 都必须保留原始 txt 的全部 HTML 标签（`em`、`r` 等一个不少）。B. 中日双语 TXT 用来放进游戏做汉化，在本地完成，必须去掉全部 HTML 标签并保留菜单4的 `\n` 检查。
> 状态图例：✅ 完成 · 🔄 进行中 · ⬜ 未开始 · 🔒 需你本人操作（涉及账号/密钥）

---

## 一、需求（我要什么）

1. **在线编辑**：成员用浏览器打开剧情，直接改译文，不再传文件
2. **GitHub 账号加入**：成员加为仓库 collaborator，有写权限
3. **不走 PR**：collaborator 直推，省掉审 PR 环节
4. **认领制**：新剧情可"报名"认领，谁在翻哪篇一目了然（GitHub Issues self-assign）
5. **只分工序不分角色**：任何人都能接翻译或校对；文档按 `待翻译→翻译中→待校对→校对中→完成` 流转
6. **按身份自动拿到工作**：登录后在 viewer 里看到"我认领的剧情"并直接打开
7. **全自动上游**：Campus 新文本自动检测、AI 机翻、进入工作台
8. **纯中文录屏线**：全在线完成；AI机翻 CSV、人工翻译 CSV、人工校对 CSV、最终录屏 TXT 都不得去除 HTML 标签
9. **中日双语游戏线**：本地完成；输出必须去掉全部 HTML 标签，并保留本地菜单4的 `\n` 一致性检查
10. **先本地跑通，再切 GitHub Pages** 公网部署

## 二、现有资产（已有的家底）

结论：**只需要 1 个新仓库**，就是 `gakumas-translation-work`。不要再单独建 txt 仓库；原始 txt 直接放工作仓 `raw/`，少一套权限和同步。

| 仓库 | 是否新建 | 定位 | 在本方案中的角色 |
|---|---:|---|---|
| `Gakumas-Auto-Translate` | 已有 | 自动流水线控制仓 | Campus 检测、AI 机翻、Actions、机翻底稿 `csv_data/` |
| `gakumas-translation-work` | **新建 1 个** | 协作工作仓 | 阶段目录产物 + Issues 认领台账 |
| `gakumas-viewer` fork | 已有 | 翻译前端 | 工作台、认领、翻译/校对、纯中文 TXT 下载 |
| `gakuen-adapted-translation-data-pm` | 已有 | 合规成品 CSV 仓 | 只接收本地菜单4等校验通过、符合 `\n` 换行数量要求的 CSV |
| `DreamGallery/Campus-adv-txts` | 外部已有 | Campus 原始 txt 权威源 | 只读上游 |
| 下游 chinosk6/GakumasTranslationData | 已有 | 合成发布 | 不变 |

## 三、工作流设计

```
Campus Resource/*.txt
        │
        ▼
GitHub Actions: auto_campus_pipeline.py
        │  检测新增 → 下载原始 txt → 预处理 CSV → GakumasPreTranslation AI 机翻
        │
        ├─ Gakumas-Auto-Translate/csv_data/        # 机翻底稿留档
        │
        ▼
gakumas-translation-work
        ├─ raw_txt/*.txt                           # 原始 txt
        ├─ ai_csv/.../*.csv                        # AI 机翻 CSV
        ├─ translated_csv/.../*.csv                # 人工翻译完成 CSV
        ├─ proofread_csv/.../*.csv                 # 人工校对完成 CSV
        └─ Issues                                  # 翻译/校对双轨认领
                │
                ▼
viewer 工作台：成员认领 → 编辑 → 完成时自动覆盖下一阶段目录 → 两轨完成 closed
                │
                ├─ A 纯中文录屏线：全在线
                │     Campus/raw txt → 保标签预处理 CSV → AI机翻 CSV → 人工翻译/校对 CSV
                │     最终录屏用纯中文 TXT 每次实时生成，不落库；所有 CSV 阶段和最终 TXT 都必须保留 HTML 标签
                │
                └─ B 中日双语游戏线：本地
                      走本地菜单4(双语模式)生成合规 TXT
                      去掉全部 HTML 标签，保留现有 \n 检查，再进入游戏汉化发布链
```

---

## 四、完整路线图

### A. 仓库和权限 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| A.1 | 建/确认 `gakumas-translation-work` | ✅ | 唯一新仓库；存工作 CSV、raw txt、Issues |
| A.2 | 打开 Issues + 建阶段标签 | ✅ | `待翻译/翻译中/待校对/校对中/完成`；网页端不再打“已入库” |
| A.3 | 成员加为 collaborator | ⬜ 🔒 | 你在 GitHub 邀请 |
| A.4 | 主仓配置 Actions secrets | ✅ | 已写入 `PIPELINE_PAT`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL`、`MAX_TOKENS` |

### B. 自动上游流水线 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| B.1 | Campus 新文本检测 | ✅ | `tools/auto_campus_pipeline.py --dry-run` 已能识别新增 |
| B.2 | 新 txt 下载到临时队列 | ✅ | 复用 Campus raw URL |
| B.2a | 不触碰本地 `todo/` | ✅ | pipeline 改为临时工作目录，只写最终 `csv_data/` 和工作仓 |
| B.2b | Windows 下定位 yarn | ✅ | Python subprocess 显式使用 `yarn.cmd` |
| B.3 | 本地预处理逻辑接入 CI | 🔄 | 当前复用 `preprocessor.py` 会生成剥标签的 `csv_dict`，不满足纯中文线上线 |
| B.4 | 线上保标签预处理 CSV | ✅ | `preprocess_txt_files(preserve_html=True)`，小样验证保留 `<r>`/`<em>` |
| B.4a | 预处理目录自创建 | ✅ | 线上独立跑不再依赖菜单1先建 `csv_dict` |
| B.5 | CI 自动跑 `GakumasPreTranslation` | ✅ | AI 输入前用 `GAT_TAG_n` 占位符保护 HTML 标签 |
| B.6 | 机翻 CSV 写入本仓 `csv_data/` | ✅ | 真实 API 小样通过：占位符还原后 `<r>/<em>` 标签一致 |
| B.7 | 机翻 CSV + raw txt 推工作仓 | ✅ | 新任务写入 `raw_txt/` + `ai_csv/`；旧 `raw/` + `data/` 兼容读取 |
| B.8 | 自动创建认领 issue | ✅ | 一话一个 issue，含 `<!-- path: ... -->` |
| B.9 | 真实小批量端到端验证 | ✅ | `adv_cidol-hume-3-018_01` 已进工作仓 issue #13；35 行标签校验 0 错 |
| B.10 | Actions 临时 clone git 身份 | ✅ | 修复远端 seed commit 缺 author；非无改动失败不再吞掉 |
| B.11 | 远端 Actions 验收 | ✅ | run `28914392643` 成功；`01.csv/02.csv` 和 raw txt 已在工作仓，两个 AI CSV 标签校验 0 错 |

### C. 网页工作台 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| C.1 | 工作台首页 | ✅ | 读取工作仓 Issues |
| C.2 | 翻译/校对双轨认领 | ✅ | issue body 存 `tr/pr` 状态 |
| C.3 | 编辑器直推工作仓 | ✅ | collaborator 直接保存，不走 PR |
| C.4 | 未认领/未解锁只读 | ✅ | 未认领的人不能编辑；即使直接打开 URL 也不能提交 |
| C.5 | 两轨完成自动 closed | ✅ | 进入“已完成”下载区，不在网页端入库 |
| C.8 | 各阶段下载按钮 | ✅ | 翻译栏下载 AI CSV，校对栏下载翻译 CSV，成品栏下载校对 CSV + 实时纯中文 TXT |
| C.6 | 浏览器加载工作台 | ✅ | 本地 viewer 已启动，工作台页面可打开 |
| C.7 | 浏览器登录工作台 | ⬜ 🔒 | GitHub OAuth 停在登录页，需要你手动登录一次；后端权限已用 `gh` 验证 |

### D. 纯中文录屏线 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| D.1 | 网页端下载成品 CSV | ✅ | 从工作仓当前版本下载 |
| D.2 | 线上保标签预处理 CSV | ✅ | 取代本地第2步；不生成剥标签的 `csv_dict` 作为纯中文线输入 |
| D.3 | AI机翻 CSV 保标签 | ✅ | 中间 CSV，不是 TXT；真实 API 小样验证保留标签 |
| D.4 | 人工翻译 CSV 保标签 | ✅ | 翻译完成时自动覆盖 `translated_csv/` 对应文件 |
| D.5 | 人工校对 CSV 保标签 | ✅ | 校对完成时自动覆盖 `proofread_csv/` 对应文件 |
| D.6 | 网页端生成最终录屏 TXT | ✅ | 不存 `final_txt/`；每次用 `raw_txt/` + `proofread_csv/` 实时生成 |
| D.7 | HTML 标签一致性校验 | 🔄 | AI输出、网页保存/完成、TXT下载/生成都会拦截；提示需细化到行号和缺失/多余标签 |
| D.8 | 批量下载纯中文 TXT | ⬜ | 单个下载先修正确，再做批量 |

### E. 中日双语游戏线 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| E.1 | 明确双语 TXT 规则以本地 `process_bilingual` 为准 | ✅ | 游戏用 TXT 在本地完成 |
| E.2 | 在线协作产出的 CSV 可作为双语线输入 | ✅ | 工作仓 CSV + raw/Campus 原始 TXT |
| E.3 | 本地菜单4(双语模式)生成合规 TXT | ✅ | 当前仍是可靠路径 |
| E.4 | 去掉全部 HTML 标签 | ✅ | 保留本地 `clean_html_tags` 逻辑，不搬网页 |
| E.5 | 保留菜单4的 `\n` 一致性检查 | ✅ | 原文/译文末尾 `\n`、行数检查必须保留 |
| E.6 | 双语 TXT 下游合成/游戏内回归 | ⬜ | 复用现有下游，不重建 |

### F. 成品入库边界 ✅
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| F.0 | 创建 viewer fork | ✅ | `chihya72/gakumas-viewer` 已创建，权限 ADMIN |
| F.1 | 移除网页端一键入库 data-pm | ✅ | 已完成文件只允许下载 CSV/纯中文 TXT |
| F.2 | data-pm 入库留在本地校验后 | ✅ | 只收符合 `\n` 换行数量要求的 CSV |
| F.3 | 已完成区显示翻译/校对人 | ✅ | 工作台显示个人 ID，不显示 GitHub ID |

### G. 公网部署 ⬜
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| G.1 | 自建 GitHub OAuth App | ⬜ 🔒 | 你申请 Client ID/Secret |
| G.2 | viewer `.env` 换生产 OAuth/仓库配置 | ⬜ | 填你的值 |
| G.3 | GitHub Pages 部署 workflow | ⬜ | 我写 |
| G.4 | 全流程公网回归 | ⬜ | 登录、认领、保存、完成、纯中文下载 |

---

## 四点五、工作台二期（2026-07-08 新定稿，已开工）

> 用户层原则：**目录表示产物阶段，issue 表示认领状态，commit/hash 只做后台历史追溯**。
> 普通用户不需要理解 commit/hash，也不需要手动搬文件。
> 重做时直接覆盖 `translated_csv/` 或 `proofread_csv/` 对应文件；旧版本只从 git 历史里找。

### 工作仓库目录定稿

```text
gakumas-translation-work/
  raw_txt/            # 原始 txt
  ai_csv/             # AI 机翻 CSV，Action 自动创建/覆盖
  translated_csv/     # 人工翻译完成 CSV，点“翻译完成”自动创建/覆盖
  proofread_csv/      # 人工校对完成 CSV，点“校对完成”自动创建/覆盖
```

不建 `final_txt/`。录屏用纯中文 TXT 每次由网页实时用 `raw_txt/` + `proofread_csv/` 生成。

### H. 历史已完成页 ✅
> 顶栏新页面 `/history`：所有两轨完成(closed)的文件，默认按 Actions 播种时间倒序；
> 每行显示 文件名 · 译者 · 校对 · [校对CSV下载] [纯中文TXT下载]。

| # | 编写步骤 | 涉及 |
|---|---|---|
| H.1 | `listIssues` 补分页（现在 per_page=100 会截断，>100 个必丢数据，前置修复） | ✅ viewer `auth.ts` |
| H.2 | 下载 CSV / 纯中文TXT 功能接入历史页 | ✅ 直接复用现有 workflow 调用，暂不抽 helper |
| H.3 | 新建 `History.vue`：拉 closed issues → docFromIssue → 表格渲染（译者/校对用个人ID显示） | ✅ viewer 新文件 |
| H.4 | 路由 `/history` + 顶栏入口“已完成” | ✅ viewer `main.ts` `App.vue` |
| H.5 | 排序：默认按 issue number 倒序 | ✅ 后续需要再加完成时间/文件名切换 |

### I. 存档功能 ✅
> 始终没人接单、或接单后长期未完成的文件，可「存档」移出活跃列表；存档页记录当时进度；可恢复。

| # | 编写步骤 | 涉及 |
|---|---|---|
| I.1 | 工作仓库建“已存档”标签 | ✅ 已创建 |
| I.2 | 工作台每行加「存档」按钮（带确认）：加标签 + close，双轨标记原样保留 | ✅ viewer `Workbench.vue` `workflow.ts` |
| I.3 | 新建 `/archive` 存档页：列“已存档”issue，显示存档时的双轨进度 | ✅ viewer 新文件 + 路由 |
| I.4 | 存档页加「恢复」按钮：reopen + 去标签 → 回到工作台原状态 | ✅ |
| I.5 | 历史页(H)与存档页互不混入：H 过滤掉“已存档”标签 | ✅ |

### J. 阶段目录与下载按钮 ⬜
> 每个状态都给对应下载入口；完成动作自动写下一阶段目录，不需要人工搬运。

| # | 编写步骤 | 涉及 |
|---|---|---|
| J.1 | seed/Action 输出改为 `raw_txt/` + `ai_csv/`；issue body 记录 `raw_path` / `ai_path` / `translated_path` / `proofread_path` | ✅ 本地真实跑通 `adv_cidol-hume-3-018_03`，工作仓 issue #17，标签校验 0 错；Actions run `28949682890` no-op 回归成功 |
| J.2 | 翻译完成：保存当前 CSV，并覆盖写入 `translated_csv/` 对应文件；然后更新 issue 翻译轨状态 | ✅ viewer `TranslationPanel.vue` `workflow.ts` |
| J.3 | 校对完成：保存当前 CSV，并覆盖写入 `proofread_csv/` 对应文件；然后更新 issue 校对轨状态并 close | ✅ viewer |
| J.4 | 工作台翻译栏加 [AI机翻CSV] 下载按钮，来源 `ai_csv/` | ✅ viewer `Workbench.vue` |
| J.5 | 工作台校对栏加 [翻译CSV] 下载按钮，来源 `translated_csv/`；翻译未完成时置灰 | ✅ viewer `Workbench.vue` |
| J.6 | 已完成栏加 [校对CSV] [纯中文TXT] 下载按钮；TXT 实时生成，不落库 | ✅ viewer `Workbench.vue` |
| J.7 | 重做规则：再次完成翻译/校对时覆盖 `translated_csv/` / `proofread_csv/` 同名文件；不保留并列旧文件 | ✅ viewer `workflow.ts` |

### K. 个人ID绑定 ⬜
> 组员随时自助设置个人ID；工作台显示个人ID，不显示 GitHub ID。后续权限管理也依赖它。

**存放**：工作仓库根 `users.json`：`{ "<github登录名>": { "name": "<个人ID>", "role": "member|pm" } }`。

| # | 编写步骤 | 涉及 |
|---|---|---|
| K.1 | 工作仓库建初始 `users.json`（现有成员+你，role 先都填好） | 🔒 或我代跑 |
| K.2 | `fetchUsers()` + `updateMyName()`：读改写自己条目，sha 冲突重试复用 updateContent | viewer `workflow.ts` |
| K.3 | 设置入口：顶栏头像下拉加“个人设置”，输入个人ID→保存→即时生效 | viewer `PushHeader.vue` 或新组件 |
| K.4 | `displayUser` 改读远程 users.json，删硬编码字典 | viewer 全局替换 |

### L. 权限与 PM 管理 ⬜
> PM 可以：主动上传新文档、修改任意文件的译者/校对、存档/恢复，方便整理归档。

| # | 编写步骤 | 涉及 |
|---|---|---|
| L.1 | 依赖 K：users.json 的 role 字段 + `isPm` 判定 | viewer `workflow.ts` |
| L.2 | 未认领/非本人编辑限制：页面只读；即使直接打开 URL，也不能提交 | viewer `TranslationPanel.vue` |
| L.3 | PM 管理操作（仅 PM 可见）：改派/清空 译者·校对、直接置某轨状态、存档/恢复任意文件 | viewer `Workbench.vue` 等 |
| L.4 | PM 上传新文档 v1：网页上传 CSV → 推 `ai_csv/` 或指定阶段目录 + 自动开认领 issue | viewer 新组件 |
| L.5 | 批量选择+批量存档（依赖 I） | 后续迭代 |

### 暂不做 / 明确不考虑

| 项目 | 结论 |
|---|---|
| final_txt 落库 | 不做；纯中文 TXT 每次实时生成 |
| 在线 `\n` 数量检查 | 不做；这个工作流只给录屏组 |
| 线上入 `data-pm` | 不做；`data-pm` 仍只收本地合规检查后的 CSV |
| 手动搬阶段文件 | 不做；由完成按钮自动写入阶段目录 |
| 并列保存旧版 CSV | 不做；重做直接覆盖，旧版看 commit 历史 |
| 直接 GitHub 手改导致状态错乱 | 暂不考虑 |

**建议实施顺序**：H.1 分页（前置缺陷）→ J（阶段目录与下载按钮）→ K（个人ID/权限基础）→ H（历史页）→ I（存档）→ L（PM 管理）。

---

## 五、历史任务进度表

### 阶段 0：环境搭建（本地跑通） 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 0.1 | clone viewer 到 D:/GIT/gakumas-viewer | ✅ | |
| 0.2 | yarn 装依赖 | ✅ | |
| 0.3 | `.env` 数据源指向我的仓库 | ✅ | index/dir→data-pm，pretrans→Gakumas-Auto-Translate/csv_data |
| 0.4 | 本地 dev 5173 启动 + launch.json | ✅ | `node scripts/compileMd.js` 补 changelog |
| 0.5 | 验证机翻底稿/成品两类入口能加载编辑 | ✅ | snapshot 逐行渲染正常 |
| 0.6 | 实测 GitHub 登录 | ✅ | OAuth 登录成功、目标仓库正确、token 交换正常 |
| 0.7 | ~~原生 fork+PR 推送~~ 废弃 | ✅ | owner 不能 fork 自己仓库；且模型走 PR，与需求冲突 → 改直推(阶段2.4) |

### 阶段 1：工作仓库与认领台账 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 1.1 | 播种脚本 `tools/seed_work_repo.py`（建仓/推文件/开Issue，per-story） | ✅ | 干跑通过；路径映射 csv_data→data/adv/story/NN.csv |
| 1.2 | 工作仓库只跟踪**新增/在做**剧情，非全量 1973 | ✅ | 定案：checker 检测新剧情时入库+开Issue |
| 1.3 | 建工作仓库 `gakumas-translation-work` + 5 label + 播种测试批 | ✅ | public；用户自建空仓，已 seed amao-3-000/001/002 共3篇+3 issue，raw 200 |
| 1.4 | 成员加为工作仓库 collaborator | ⬜ 🔒 | 你在 GitHub 邀请 |
| 1.5 | run.py 检测新剧情时调 seed_work_repo（--push --issues） | ⬜ | 扩 checker.py，接现有菜单 |
| 1.6 | 收割脚本 harvest_work_repo.py + run.py 菜单7 | ✅ | 两轨完成的closed issue→下载CSV到todo/translated/csv→打"已入库"标签→接菜单4/5 |
| 1.7 | ~~网页端一键入库~~ | ✅ 废弃 | data-pm 只能存放符合 `\n` 换行数量要求的 CSV，网页端不入库 |
| 1.8 | **网页端下载成品CSV/纯中文TXT** | ✅ B14 | 已完成区只提供下载，纯中文 TXT 保标签生成 |
| 1.9 | **上游接 campus 权威源** | ✅ B13 | 原始txt源=DreamGallery/Campus-adv-txts/Resource；viewer fetchRawTxt campus优先+工作仓库raw/兜底 |
| 1.10 | **自动流水线 Action** | ✅ | `.github/workflows/campus-to-work.yml` 定时/手动跑 Campus→AI→工作台 |

### 阶段 2：viewer 认领功能 🔄
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 2.1 | 工作台首页（我的任务/可认领/进度总览），调 Issues API | ✅ | Workbench.vue；'/'路由改为工作台，原首页移 /browse |
| 2.2 | 任务链到剧情编辑器 URL（issue body 里 `<!-- path: -->` 标记） | ✅ | workflow.ts editorUrlForPath |
| 2.3 | 认领=self-assign+换标签；完成本阶段=换标签+取消assign | ✅ | listIssues/updateIssue；vue-tsc 通过；待实测 |
| 2.4 | 改 PushPanel：collaborator 直推，跳过建 PR | ✅ | 新 DirectPush.vue「保存=写回源路径」；vue-tsc 通过；待实测 |

### 阶段 3：标签保全（em/r 标签坑） ✅
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 3.1 | 明确两套产物对标签的要求 | ✅ | 纯中文录屏线线上全程保标签；中日双语游戏线本地去标签 |
| 3.2 | AI 机翻 CSV 标签保护 | ✅ | `GAT_TAG_n` 占位符保护标签，输出后还原并校验 |
| 3.3 | 人工编辑/校对标签保护 | ✅ | viewer 保存/完成前校验 `text/trans` 标签序列 |
| 3.4 | 最终纯中文 TXT 标签保护 | ✅ | 生成时先校验 CSV 行，再校验最终 TXT 与 raw txt 标签序列 |

### 阶段 4：公网部署（GitHub Pages） ⬜
| # | 任务 | 状态 | 说明 |
|---|---|---|---|
| 4.1 | 自建 GitHub OAuth App（回调指向 Pages 域名） | ⬜ 🔒 | 你申请 Client ID/Secret |
| 4.2 | `.env` 换生产 CLIENT_ID/SECRET/HOSTNAME | ⬜ | 填你的值 |
| 4.3 | build + GitHub Pages 部署工作流 | ⬜ | 我写 workflow |
| 4.4 | 全流程公网回归测试 | ⬜ | |

---

## 六、当前位置

**（2026-07-08 追加）工作台二期 H–L 已按阶段目录方案重写（见"四点五"）。H.1/J/H/I 已完成；剩余 K 个人ID/权限基础、L PM 管理。**


**目标已落地到可验收版本：全自动上游 + 网页工作台 + 两套最终产物。新仓库只保留 `gakumas-translation-work` 一个。**

两条产物线当前状态：
- A 纯中文录屏线：已在线打通。Campus 新文本可自动入临时队列，保标签预处理，AI 机翻，写入 `csv_data/`，推送到工作仓 `data/` + `raw/`，创建认领 issue。AI机翻 CSV、人工翻译 CSV、人工校对 CSV、最终录屏 TXT 都走标签一致性校验。
- B 中日双语游戏线：继续本地完成；本地菜单4的去标签逻辑和 `\n` 检查保留，不搬网页。

直推模型（关键设计）：「保存」= 把当前译文写回它被读取的那个 github 路径（同 owner/repo/branch/path），
用 Contents API PUT（`updateContent`），不 fork/不建分支/不走 PR。直推只用于工作仓；`data-pm` 不从网页端入库。
成员只需对目标仓库有写权限（collaborator）。并发靠 Issue self-assign 软锁（一文件一人）。

改动文件（都在 D:/GIT/gakumas-viewer）：
- `src/store.ts` +sourceUrl
- `src/helper/source.ts` 远程 github csv 源时记录 sourceUrl
- `src/helper/path.ts` +parseGithubBlobUrl（健壮解析，替代写死深度的 extractInfoFromUrl）
- `src/components/translate/push/DirectPush.vue` 新增（一键提交）
- `src/components/translate/push/PushPanel.vue` 换用 DirectPush
- 遗留 dead：BranchController/CommitCard/PullController/PushSteps 已无引用，可删

已完成验收：
1. GitHub secrets 已配置：`PIPELINE_PAT`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`MODEL`、`MAX_TOKENS`
2. 本地真实流水线跑通 `adv_cidol-hume-3-018_01`，工作仓 issue #13，标签校验 0 错
3. 远端 GitHub Actions run `28914392643` 成功，生成 `adv_cidol-hume-3-018_02`，工作仓 issue #14，标签校验 0 错
4. viewer fork `chihya72/gakumas-viewer` 已推送 `gkmas` 分支；本地页面可打开，保存/完成/TXT生成都会拦截标签不一致

剩余必须你本人操作：
1. 在网页工作台完成一次 GitHub OAuth 登录
2. 邀请协作者加入 `gakumas-translation-work`
3. 申请生产 GitHub OAuth App 后，我再补 GitHub Pages 部署与公网回归
