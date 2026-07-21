# Canvas Pilot — 产品架构 + 功能规格书（单一真相源 / Codex 导向）

> **状态**：ACTIVE，2026-07-18 已完成 Codex 主运行时迁移与隔离 Canvas 端到端验收。
> **取代**：`docs/NORTH_STAR.md`、`docs/CANVAS_PILOT_CLAUDE_FUNCTIONS.md`、`docs/CODEX_MASTER_PLAN.md`、`_private/decisions/north-star.md`、`_private/decisions/Claude Code-Codex 生态.md` 中关于「产品是什么 / 怎么运转 / 有哪些能力」的部分。这些文件保留作历史，新读者以本文为准。
> **隐私**：本文是 tracked、公开安全文件。**不得**含真实身份、学校、邮箱、真实课号、instructor 名、机器 UUID。具体值只在 gitignored 的 `SECRETS.md` / `courses.yaml` / `_private/` 里。
> **读者**：本文的首要读者是 **AI agent（Codex）**。它要能照着本文理解并重建整个产品。

---

## 0. 一句话

Canvas Pilot 扫描学生的 Canvas LMS、把本周要交的作业排成计划、等学生批准后把每一项派给对应的「课程技能」完成并验证可审草稿；只有学生随后对一个精确目标另行授权时才提交。日常执行时学生分别决定「做什么」和「交什么」；首次配置时还要从本地机会榜单选择「先固化哪个重复模式」。

默认行为是**完成到可审草稿、你决定是否提交**。计划批准永远不是 Canvas 写权限；交互提交必须来自后续的精确命令、有效签名 receipt、验证闸和 Canvas 读回。

---

## 1. Driver 模型（重要：Codex 现为唯一主力）

本产品最初长在 **Claude Code** 上，依赖它的技能调度、子任务、hook 拦截、审批边界等专有机制。

**2026-07 迁移结果**：维护者迁往无法访问 Claude/Anthropic 的环境，**Codex 已成为唯一主力 driver**。因此：

- 之前「双轨 sidecar、做题技能只留 Claude」的策略（旧 `生态.md §8`）**已作废**。
- setup、scan、execute、课程做题、humanizer、提交/quiz、cron 和开发护栏均已有 Codex-native 路径。
- `.claude/` 保留不动作为冻结历史与可恢复旧路径；Codex runtime 不读取它。

两个 driver 的目录边界：

```
.claude/   settings.json · hooks/ · skills/ · agents/   ← 旧 driver（保留，冻结）
.codex/    config.toml · hooks.json · hooks/            ← 新 driver 配置 + 护栏
.agents/   skills/<name>/SKILL.md                       ← 新 driver 技能（Codex 扫 cwd→repo root）
CLAUDE.md  Claude 入口    AGENTS.md  Codex 入口
src/       driver 无关的 Python 原语（两边共用，不复制）
```

Codex 运行时事实（2026-07-18 本机实测，Codex CLI 0.144.5）：
- repo 技能放 `.agents/skills/<name>/SKILL.md`（每个 SKILL.md 必须有 `name` + `description`）。
- repo hook 放 `.codex/hooks.json`；`.codex/config.toml` 用 canonical
  `[features].hooks = true`（TOML 文件中是 `[features]` 表下的
  `hooks = true`），fresh subprocess 显式传 `--enable hooks`。旧
  `[features].codex_hooks` 已弃用，不得新增。
- 本仓实际注册 `SessionStart`、`PreToolUse`、`PostToolUse`、`Stop` 四类事件；不把平台可支持事件数与仓库注册数混写。
- custom prompts 已废弃 → 一律用 skills。
- hooks 与 `AGENTS.md` 实测加载；另一个完全不含 `.claude/` 的 fresh workspace 已完成真实只读 scan。
- ✅ Codex **有**原生并行 subagent（定义在 `.codex/agents/*.toml`，2026-03-16 上线）——1:1 映射 Claude 的 `Agent(subagent_type=...)`，见 §8 能力映射。

---

## 2. 给谁用 / 立场

- 学校用 Canvas LMS 的学生。
- 课业里**重复结构**作业占比高（每周题集、每周阅读、每周 quiz、教材习题）。
- 想让 AI 接管枯燥的编排（扫描、派发、出草稿），但**审阅与提交牢牢握在人手里**。

立场：系统会完成用户明确批准的作业到可审草稿，但不会替用户决定做哪项、
不会把计划批准扩张成提交权，也不会静默交付。它不是要求每个 fork 用户自己
重写全部课程逻辑的研究框架；更接近「学校版日历 + 一个已经认识这些重复作业
类型、且提交权被机械隔离的助手」。学术诚信判断是运行者自己的事，框架对此
中立、不内置政策筛查。

---

## 3. 端到端产品流程

首次 fork/clone 使用安装页的精简提示词：下载仓库后先问用户在哪所学校使用
Canvas，解析学校官方 Canvas 登录地址（只有不明确时才问 URL，绝不猜），再在
浏览器完成登录；鉴权成功后立即运行 opportunity 分析。日常入口仍是在仓库目录
的 agent 会话里说 `scan canvas`。两条入口共享同一组鉴权、选型和审批边界。

```
首次安装提示词：下载/更新仓库
未配置仓库里的 "scan canvas"：使用现有仓库
  └─ canvas-setup：先问学校 → 解析学校官方 Canvas 地址
       └─ 地址不明确：问用户 Canvas URL，绝不猜
       └─ 本地配置 → 受保护凭据 → 浏览器登录 → 鉴权验证
            └─ 鉴权成功且 routes 空 → 立即运行 canvas-skill-opportunity
            ├─ 只读发现 recurring candidates
            ├─ 检查足够的代表性真实 spec + 安全的 Canvas feedback-policy 投影
            ├─ Agent 按证据做定性判断，recurrence / future value 只用于同档排序
            ├─ 写 runs/<today>/skill-opportunities.{json,md}
            └─ STOP，等待用户选择编号

用户在下一轮选择编号
  └─ canvas-bootstrap：验证真实 spec / 材料 / 可重复流程 / 数值检查
       ├─ viability gate 失败 → 不建 ready route，提供下一候选
       └─ 通过 → 每次只配置一个 course skill + local route

routes 非空后的 "scan canvas"
  └─ 列 pending → 写 plan.json → STOP
       用户批准做哪些项 → canvas-execute 派发 → 验证草稿
       → 每项 result.json → REPORT.md + final_drafts/ → STOP

用户之后另发一个精确 mutation 命令
  └─ submit N | take quiz N | retake quiz N
       → canvas-submit 重验当前 plan + 本地证据
       → 生成短期、target/action/session 精确的签名 receipt
       → 单目标 Canvas 写入 → 权威读回 → receipt 终态消费 → result.json
```

四个非显然点：

1. **首跑选型是只读证据审查，不是 pending 作业扫描**。`canvas-skill-opportunity` 先发现重复模式，再只读检查足够的代表性真实说明与材料入口，判断任务实际要求；Quiz 等候选还可读取经过脱敏投影的重试/反馈策略事实。它不启动 attempt、不做题、不读取或保留原始答案与精确成绩、不上传/提交，也不在用户选号前创建 route/skill。私有报告写到 gitignored 的 `runs/`，聊天只显示编号别名。

2. **审批是文件系统边界，不是 prose**。`canvas-scan` 写 `plan.json` 后**停**；`canvas-execute` 在用户回复批准后才读它。两次独立的技能调用，用户能在中间打断。这是 2026-04-21 runaway 事故后的硬架构修复（当时一个技能在同会话里边扫边派，容量爆了、7 项失败）。

3. **`canvas-bootstrap` 故意单 cluster**。一个学生通常 3–4 门可跟踪课。一次配一门、走开、明天再配下一门，每次都有可交付物，还能复用上一门学到的东西。

4. **每个课程技能第一次跑是和你共创，不是一锤子**。bootstrap 的 overlay v1 是技能读完 cluster 的最佳猜测；v2 是你看过一份真草稿、反馈被分类后才有的。首跑校准环约 30 分钟/cluster；之后同技能非交互。

5. **做题批准和 Canvas mutation 是两种权力**。`all`、`1,3` 或
   `approve 2` 只允许本地草稿工作。交互写入只接受后续整条消息中的
   `submit N`、`take quiz N` 或 `retake quiz N`，且一个 receipt 只绑定一个
   origin、session、course、assignment/quiz 和动作集合。初次 quiz receipt
   不含 `quiz.retake`。

**首跑校准环**（bootstrap 内）：派课程技能出一份草稿 → 你审阅给反馈 → Sub-agent D 把每条反馈分类（`recurring_pattern`→写回 overlay v2 / `one_off`→只改这份 / `workflow_change`→写回 overlay v2）→ 你确认 → `first_run_calibration_done=true`。

**Opportunity 判断协议**：最终推荐来自 Agent 对真实证据的判断，不由固定权重或 0–100 程序分数决定。

- 默认强候选包括：可由 Canvas 交付的代码、以客观题为主的 Canvas Quiz、数学/会计/经济/统计/金融等定量题、结构化 Word/Excel/PDF 商科作业，以及由多个独立短答或短批注组成的作业。
- 判断文字负担时看**最大的连续 prose 单元**，不看整份作业总字数。一个主要连续文字单元约 200 词以上是强降级信号；许多各 10–40 词的独立批注或短答即使总字数更高，也不因此降级。代码、公式、表格与项目符号不按连续 prose 处理。
- 不要求存在正式 regression harness。代码运行、独立重算、会计勾稽、统计/经济关系检查、材料交叉确认和 rubric 覆盖都可作为提交前复核。
- 提交后闭环可显著提升候选：例如多次尝试、下一次尝试前可见成绩/逐题反馈、且计分采用最高分。Opportunity 只看 `allowed_attempts`、反馈可见时机、答案可见性和计分策略等安全派生事实；绝不为了探测策略而发起 attempt。
- 先处理硬阻断与任务适配，再看数字化交付、复核/反馈闭环和重复稳定性；future count、已知分值与节省时间只用于同等候选之间排序，不伪装成成绩预测。

---

## 4. 技能目录

技能 = 给 agent 的 Markdown 指令。分三类。

### 4.1 框架技能（通用，任何课原样用）

| 技能 | 职责 |
|---|---|
| `canvas-setup` | 首跑先问用户在哪所学校使用 Canvas，解析学校官方登录地址；不明确时才问 URL，绝不猜。随后完成本地配置、受保护凭据、浏览器登录与鉴权验证；鉴权成功且 routes 空时立即交给 opportunity 分析，自己不扫描作业。 |
| `canvas-skill-opportunity` | 只读发现重复候选，检查代表性真实 spec 与安全的 Canvas feedback-policy 投影，由 Agent 给出定性 first-skill 建议；写私有本地报告并在用户选编号前停下。 |
| `canvas-bootstrap` | 用户选中候选后验证真实 spec、材料、可重复流程和检查方式；viability gate 通过才起草一个 public-safe course skill 与本地 route。含首跑校准环。 |
| `canvas-scan` | 读 `courses.yaml`、查 Canvas pending、写 `plan.json` + `assignments.json`、渲染计划表、**停**。routes 空时派 opportunity，不直接派 bootstrap。 |
| `canvas-execute` | 读用户批准 vs `plan.json`、派发已批准项到 per-course 技能、汇总结果、写 `REPORT.md`、同步 `final_drafts/`。**唯一把已批准作业派给课程做题技能的地方**。 |
| `canvas-submit` | 只处理用户之后另发的一个精确 `submit N` / `take quiz N` / `retake quiz N`；重验 plan 与草稿，签发 target-exact receipt，执行一个 Canvas mutation 并读回。 |
| `canvas-cron` | 安装、检查、暂停、修改或删除 scan/email/autonomous 模板；默认 disabled-first，dry run 无副作用。自主提交还要求显式 durable parent receipt，并为每项派生短期 child receipt。 |
| `canvas-skip` | 把作业打到手动处理：写 `runs/<today>/todo.md`、返回 `skipped`。用于 Lockdown Browser 等 intrinsic can't-do。 |

### 4.2 课程骨架技能（通用框架 + 本地 overlay）

每个是一类课的通用框架；学校/instructor 专有行为写在 gitignored 的 `_private/canvas-<name>-app.md` overlay 里，第一步加载。overlay 不存在则技能停下并要求作者化（或派 `canvas-bootstrap` 交互起草）。**骨架本身公开安全，不含私有数据。**

下文的「submit（若授权）」专指当前 target/action/session 的有效签名
receipt；不包括 `plan.json` approval、环境开关、旧对话或模糊 standing
permission。没有 receipt 时所有课程技能停在本地验证草稿。

- **`canvas-ics33` — 代码课**：spec 在 Canvas 外（instructor 站 / 附件 PDF / 教材），下载脚手架、带测试覆盖写代码、打包提交。语言无关（Python/Java/JS/Rust/Go 同一条 9 阶段流水线，overlay 指定测试器/构建/提交格式）。
  - `fetch-spec → fetch-references → download-scaffold → constraints-checklist → test-first implement → process_humanize（仅 process-graded 课）→ audit（标识符接地 + 数值约束 + 覆盖）→ bundle + re-clone verify → submit（若授权）`
- **`canvas-reading-annotation` — 写作课（PDF 批注）**：色标高亮 + 旁注 + 填空，按 instructor rubric。
  - `classify → locate_reading → extract_text_and_blanks → annotate_pdf → fill_answer_blanks（目标 voice，≥90% 行宽）→ verify（6 闸：行填/旁注密度/色系/页数/无重叠/无 sticky icon）→ submit（若授权）`
- **`canvas-essay` — 写作课（长文）**：autoethnography / 反思 / 批判分析 / 研究论文。
  - `load_persona → parse_spec → load_sample_essays → generate(outline→body→revise) → figure_captions + works_cited → verify（字数/引用数/图注数）→ output(.docx/.pdf) → submit（若授权）`
  - `src/ac_eng_router.py` 用确定性 6 层级联把写作课作业路由到 reading-annotation（短/批注型）或 essay（长文）。
- **`canvas-zybooks` — zyBook 数学/离散课**：Canvas description 是习题引用表，交付物是解出的题渲染成 PDF。
  - `classify → fetch-spec(描述表 OR 附件 PDF) → fetch-exercises(zyBook API) → solve → render-LaTeX-PDF → verify(子题数/无占位泄漏) → draft-only(GradeScope 手动上传)`
- **`canvas-inside` — Canvas 在线 quiz**：学生授权 auto-take 的开放 quiz（MCQ/多选/判断/匹配/简答/作文）。
  - `classify → 4 安全闸(autorun/human-hours/per-cron rate/whitelist) → reading discovery(4 层) → study_notes.md → 4-agent 仲裁(notes-first/grep-first/framework-aware/contrarian) → paced-submit(拟人:计时/blur-focus/序列非线性/可选 strategic miss) → complete → score-check → retake(Layer 2 gated)`
  - 提交拟人是 `src/quiz_pacing.py` / `quiz_focus_events.py` / `quiz_strategic_miss.py` 里的命名 helper；三层独立 enforcement 防绕过 4-agent 仲裁。

### 4.3 运行时设计的兜底技能

- **`canvas-generic` — runtime-designed fallback**：不匹配任何具体技能时（bootstrap 标 `⚠ unclear` 等）由路由触发。**不读 overlay**，全程运行时调查（description+front_page+modules+syllabus+URLs）、找 rubric、下载输入、设计 per-assignment 流水线、3 个 sub-agent review、出草稿+验证日志。**从不自动提交**。token 成本约具体技能的 3×；周更 cluster 应「毕业」成具体技能。

### 4.4 Humanizer 家族（公开框架，2026-05-24 已 genericize 发布）

降低草稿的 AI 检测信号。被写作类技能在生成阶段调用。

| 技能 | 做法 |
|---|---|
| `canvas-humanizer` | 句级分段 → 每句 round-trip 翻译生成 K 候选 → Levenshtein 结构分歧选优 → 可插拔真检测器 adapter |
| `canvas-humanizer-loop` | humanizer + 3 并行 sub-agent 多数投票审计（语义/结构/rubric 损伤）→ 受损段 per-segment 重写 → 重 humanize，最多 3 轮，3 层收敛守卫 |
| `canvas-humanizer-surgical` | 二次修补：按位置分化 ESL register（gate-sensitive 位用干净语法 ESL，body 位用全 ESL）|
| `canvas-awkward-syntax` | 直接提交式句法标记重写：每句一个确定性结构变换（9 选 1），rubric-critical 位保干净、body 位激进 |

> **注意**：humanizer 家族**已公开**（不在 export-ignore）。它们是公开框架技能，不是私有做题逻辑。

---

## 5. 核心规则：`assignment.description` 几乎从不是真 spec

`assignment.name` / `description` 是**路由提示，不是 spec**。多数 STEM 课它是空串；多数非 STEM 课它是一段不告诉你要产出什么的话。真 spec 通常在别处：front page 链接的 instructor 外站 / Files 里的阅读 PDF / modules 里的 wiki 页 / 教材章节 / 作业附件 PDF。

任何课程技能处理作业前应：①读 description 但当提示；②拉 `cv.get_front_page(course_id)` 找外部指针；③拉 `cv.list_modules(course_id)` 找材料；④走遍引用（其它 Canvas 页/外链/附件）。

生产中两连夜踩过这个坑：①代码课 description 全空被标 unsupported——其实 front page 一直有外站链接；②zyBook 作业按 API 的 "suggested practice" 渲染了 162 题——instructor 在 description 第二列只指定 ~22 题。两次都因「相信看起来像 spec 的东西、没走引用」。

---

## 6. 运行状态机械契约（Codex 主运行时）

所有状态都是本地文件（JSON/Markdown/文件夹）。无数据库、无云、无远程备份。`.claude/` 仅保留历史兼容；当前机械真相源是 `src/run_state.py` 与 `docs/RUN_STATE_SCHEMA.md`。

### `runs/<today>/skill-opportunities.{json,md}` — 首次配置机会榜单

`canvas-skill-opportunity` 写，`canvas-bootstrap` 在用户选号后读。它只用于选择先固化哪个重复模式，**不是** `plan.json`，不构成任何作业批准或提交授权。报告保存定性 recommendation、任务类型、代表性 spec 证据、最大连续 prose 单元、数字化交付路径、提交前复核方式、脱敏后的提交后反馈策略、重复性、future value 与未知项。真实课程名、ID 和私有证据只留在 gitignored 的本地报告；聊天中只用编号别名。原始答案、精确成绩和私有反馈正文不得进入 opportunity 报告。用户选号后，bootstrap 仍必须重新验证真实 spec、材料、可重复流程和检查方式。

### `runs/<today>/assignments.json` — scan 选中的作业快照
```json
[{"course_id":12345,"course_name":"Course Name","assignment_id":67890,
  "name":"Assignment Name","due_at":"2026-04-29T23:59:00Z",
  "submission_types":["online_upload"],"points_possible":10,"skill":"manual_skip"}]
```
scan 写；execute / Stop gate / 子技能 读。**单凭它不构成批准。**

### `runs/<today>/plan.json` — 用户可审计划
scan 写、execute 读。每项初始 unapproved；execute 派发前必须有显式批准。

### `runs/<today>/course-<course_id>__assignment-<assignment_id>/result.json` — 单作业完成契约
```json
{"status":"draft_ready"}
```
合法 `status`：`draft_ready` / `submitted` / `skipped` / `error`。
- `draft_ready` 必须有非空实质 `draft_path`、无 sentinel/placeholder，且
  `verification.log` 至少一条 `PASS`、零条 `FAIL`。
- 新 `submitted` 必须有真实 `submitted_at`、receipt ID、
  `authorization_consumed=true`、Canvas workflow state 与
  `readback_verified=true`；`graded` 只能作为 metadata，不能成为 status。
- 只读发现已提交用 `status=submitted` + `reason_code=already_submitted`，
  不得声称消费本轮 receipt。
- `skipped` 尽量带解释 notes。
- `assignments.json` 里每项最终都要有合法 result.json 才能 finalize/stop。
- quiz 专属：`kind=quiz` + `status=submitted` 还要
  `kept_score/points_possible/attempts_used/allowed_attempts` 数值、scoring
  policy、4-pass 仲裁（或逐字 degraded override）和可核验的
  `human_ness_diagnostics`。

### `runs/_processed.json` — 跨天去重 ledger
drivers 可读以总结历史；写入须保留既有条目；公开示例不得含真实 course ID。

### `runs/<today>/.scan_in_progress` — execute-mode marker
execute 原子创建、Stop gate 检查、execute 最后删除。基础字段是
`session_id`、`owner_kind=codex`、`created_at` 和完整 `plan_digest`。
在读取、复用或派发任何批准项结果前，execute 必须调用
`python -m src.run_state prepare-results`：旧批准项结果被原子移动到
`result-history/pre-<plan_digest前20位>.json`，然后 marker 原子增加
`results_prepared_at`、`results_archive_count` 和与当前 plan 精确相等的
`prepared_approved_result_keys`。该过程可恢复、同 marker 幂等，并刻意不
依赖 Windows 文件时间戳。marker 未准备、owner/digest/key 集合不匹配或
任一结果缺失时，finalize/Stop 都拒绝放行。

### 私有 mutation authority / receipt / usage ledger

一个后续精确命令会在稳定 work dir 写 `mutation_authority.json` 与
`mutation_authorization.json`。receipt 使用本地私钥签名、短期有效、绑定
Canvas origin、Codex session、单一 target 和精确 action；签名、私钥、
逐字授权和完整 usage ledger 都是 gitignored 私有数据。Canvas 每次写入
前在 API 边界 fail-closed 验签/验 scope/replay，终态提交后 usage ledger
必须显示匹配的 terminal consumption，Stop guard 才接受 `submitted`。

### `runs/<today>/REPORT.md` — 用户收尾面
列本轮发生了什么；≤24h 未交项放顶部 🔥 urgent banner；分开「已验证事实」与「判断调用」。

### `final_drafts/` — 交付文件夹
gitignored；公开示例只用通用名。

> `runs/` 与 `_private/` 都 **gitignored**——运行产物与私有 overlay 永不进 git。

---

## 7. 护栏系统（hook）

护栏在工具执行边界拦截，不只写在技能 prose 里。hook 自身的意外异常
由 `safe_main` 记录后 fail-open，避免 hook bug 锁死编辑会话；但 Canvas
mutation authorization、receipt replay/usage、run-state finalize 等关键运行时
边界在共享 Python 原语中 **fail-closed**，不依赖 hook 正常工作。

> 以下为 `.claude/settings.json` 当前实际注册的 hook（2026-06-13 核对）。注：旧 `check-bash-output.py` 已移除；`check-no-runner-script.py` / `check-source-manifest.py` / `check-setup-done.py` 为现行新增。

| 事件 / matcher | Claude hook | 作用 | Codex 对应（`.codex/hooks/`） |
|---|---|---|---|
| SessionStart | `check-setup-done.py` | 检测仓库是否未配置（.env/CANVAS_BASE）并提示派 setup | `session_start.py` ✅ |
| SessionStart | `inject-context.py` | 注入今日 pending + 跨天 ledger 摘要 | `session_start.py` ✅ |
| PreToolUse(Bash) | `check-presubmit-audit.py` | submit/upload 前必有 PASS 且无 FAIL 的 `verification.log` | `pre_tool_guard.py` ✅（含 quiz fail-closed）|
| PreToolUse(Bash) | `check-public-leak.py` | git add/commit/push 不许把私有内容/PII 推公开 | `pre_tool_guard.py` + `_lib.git_leak_issue` ✅ |
| PreToolUse(Write\|Edit) | `check-no-runner-script.py` | 禁止在 `runs/` 下建 ad-hoc runner 脚本 | `post_tool_guard.py` ✅（已含 runner-script 拦截）|
| PostToolUse(Write\|Edit) | `check-result-schema.py` | result/quiz schema、draft/verification/submission evidence | `post_tool_guard.py` + `src.run_state` ✅ |
| PostToolUse(Write\|Edit) | `check-spec-grounding.py` | spec 提引用但 `references/` 空 → block | `post_tool_guard.py` ✅ |
| PostToolUse(Write\|Edit) | `check-identifier-grounding.py` | 代码标识符不许虚构（对比 spec/references）| `post_tool_guard.py` ✅ |
| PostToolUse(Write\|Edit) | `check-source-manifest.py` | §0 required-sources 清单已取齐 | `post_tool_guard.py` ✅ |
| Stop | `check-router-complete.py` | marker owner/digest/prepared slots、每项 result、receipt terminal usage、grounding、quiz retake | `stop_guard.py` ✅ |
| （上传前显式）| agent `pre-submit-reviewer` | fresh-eye GO/WARN/BLOCK 逐 rubric 项审 | `.codex/agents/pre-submit-reviewer.toml` ✅ |

> Codex 当前安全内核已覆盖本产品依赖的 Claude 行为，并额外加入签名
> receipt、终态 usage 与 prepared-result slots。SessionStart 的展示粒度仍比
> 旧 inject-context 简洁，这是非关键 UX 差异。详见 `docs/CODEX_HOOK_PARITY.md`。
> 历史：`check-bash-output.py`（pytest 必过 / coverage 100% / git log backdate）曾存在、现已从 settings.json 移除——若 Codex 侧要等价能力，按需在 `post_tool_guard.py` 重建，不照搬已删脚本。

---

## 8. Claude → Codex 能力映射（迁移核心）

| Claude 专有机制 | 作用 | Codex 等价物 / 状态 |
|---|---|---|
| Skill tool dispatch | `canvas-execute` 调课程做题技能 | 框架技能可合法 handoff；execute 仍是唯一把已批准作业派给课程做题技能的 dispatch 点 ✅ |
| `Agent(subagent_type=...)` 并行子任务 | ics33 的 spec-verifier/quality-inferrer/audit、inside 的 4-agent 仲裁、generic 的 3 review、humanizer best-of-N | ✅ **Codex 原生 subagent**（`.codex/agents/<role>.toml` + native spawn）。并发 slot 包含主线程，不能假设四个 reviewer 永远同时可用；实测 Classic Quiz 在四 slot 环境使用三路并行 + 第四路独立顺序执行，仍保留四份独立证据。更多候选按可用 slot 分批，不降级为单一自审。 |
| Hooks（settings.json 注册）| 工具边界拦截 | `.codex/hooks.json` 注册四类事件，`[features].hooks = true`，实测可触发 ✅ |
| 审批边界（两次技能调用）| scan 停 / execute 派 | 文件系统边界与 driver 无关，原样成立 ✅ |
| SessionStart 上下文注入 | 新会话知道今天干啥 | `session_start.py` 实测注入成功 ✅ |
| `pre-submit-reviewer` agent | 上传前 fresh-eye 审 | `.codex/agents/pre-submit-reviewer.toml`，由适用课程技能在 verify 后调用 ✅ |
| 记忆 `memory/` + `MEMORY.md` | 跨会话事实 | Codex 无原生等价；候选放 AGENTS.md 约定 / `.agents/` metadata（阶段 5 决策）|
| `src/*.py` 原语 | Canvas/zyBook/quiz/humanizer 实现 | **driver 无关，两边共用，不复制** ✅ |

---

## 9. 公开/私有边界（现行单仓模型）

> 旧的「双仓 origin/upstream」表述已 STALE。现行：单 dev 仓（private）+ 公开快照。

- **公开安全**：通用 `src/*.py`、通用文档、通用框架技能骨架（含 humanizer）、用假 ID/假名的示例。
- **永不公开**：真实身份/学校/课号/作业 ID/instructor 名/邮箱、机器 UUID、`SECRETS.md`、`courses.yaml`（真 ID）、`_private/*`（含所有 overlay）、`runs/*`、`final_drafts/*`、私有事故日志。
- **机制三层**：①技能骨架本身通用无 PII；②`_private/` + `runs/` + `.cookies/` 等 gitignored，永不进 git；③发布走 `scripts/push_public_snapshot.py`——`git archive origin/main`（仅 tracked 文件、敬 `.gitattributes export-ignore`）+ **PII 审计闸**（命中真实邮箱/学校/instructor/UUID 即 ABORT）+ 单 commit force-push 到公开镜像。
- Codex 侧把骨架搬到 `.agents/skills/` **无需**加 export-ignore（骨架公开安全）；只需保证 Codex 尊重 gitignore + git 操作走 public-leak hook。

---

## 10. 鉴权模型

- **默认 cookie**：Playwright headless Chromium，持久 `.cookies/playwright-profile/`，401 时刷新。`CANVAS_REMEMBER_CREDENTIALS=false` 是默认值：不安装 username/password capture listener、不持久化密码；setup 清理旧记录并复查仅靠本地 browser session 仍可鉴权。只有用户明确 opt-in 且 DPAPI/Fernet 可用时才启用密码 autofill；base64 新写入一律拒绝。
- **备选 token**：`.env` 里 Personal Access Token，Bearer。学校禁 token 生成或学生偏好长效时用。
- 首跑下载后先问用户在哪所学校使用 Canvas，并解析学校官方登录地址；只有地址不明确时才问 Canvas URL，绝不猜。随后在 `canvas-setup` 时选择鉴权方式，默认推 cookie。

### Canvas mutation authorization

- 交互 authority 只来自当前用户后续整条精确命令；默认 TTL 15 分钟。
- HMAC receipt 绑定 canonical Canvas origin、Codex session、单一
  assignment/quiz、精确 actions 和 authority 摘要；通配 target/action 被拒绝。
- 所有 Canvas POST/PUT 都在共享 client/origin wrapper 边界验签、验 scope、
  记录 usage；assignment submit 或 quiz complete 后 receipt 终态消费，重放被拒。
- receipt 签发本身不等于消费；只有 Canvas 权威读回与 usage ledger 一致才可
  写 `status=submitted`。

### Cron authority

- `canvas-cron` 管理 scan、email、autonomous-submit 三类 Windows Task
  Scheduler 模板。安装先 disabled，dry run 必须无副作用，启动 fresh
  `run_codex`，传播真实 exit/timeout，并做 post-state verification。
- scan/email 不获得 Canvas 写权限。autonomous-submit 必须由用户显式创建
  durable automation parent receipt；每个任务运行时再为一个精确 item 派生
  短期 child receipt。默认仍关闭，普通交互 receipt 不能升级成 durable authority。

---

## 11. 范围内 / 外

**做**：首次鉴权后只读发现重复模式，检查足够的代表性真实 spec 与安全派生的 Canvas feedback-policy 证据，由 Agent 给出 first-skill 定性建议并停在选号前；扫所有配置课的 pending（可配窗口）；按紧急度分桶 + 提议技能；批准前暂停（文件系统边界）；顺序跑课程技能完成并验证草稿；收到后续精确 target/action 命令和有效 receipt 后可提交一个目标；写每日 REPORT.md（urgent banner）；镜像草稿到 final_drafts/；用 disabled-first cron 做 scan/email，或在 durable authority 下做显式 autonomous workflow。

**不做**：机会分析不启动 attempt、不做题、不读取或保留原始答案/精确成绩/私有反馈正文、不上传或提交、不在用户选号前创建 route/skill；未经计划审批不处理待办作业或执行 live action；overlay 没显式授权 + 验证闸没过就自动提交；替你做学术诚信判断（中立、不内置政策筛查）；把作业/草稿/凭据存任何远程服务；在真 Canvas 行为重要处用 mock（集成测试用录制 fixture / sandbox 课）。

---

## 12. 设计原则（跨版本不变）

- **技能是流水线不是单体**：研究→提纲→草稿→humanize→验证，每阶段独立可调可换可查；overlay 定制具体阶段。
- **审批是文件系统边界**：scan 写 plan.json 停、execute 读，两次调用、可打断。
- **默认草稿、交互提交需短期 target-exact receipt**：自动提交从不是静默默认；只有 cron 可在用户显式创建的 durable parent authority 下派生短期 child receipt。
- **scope-first onboarding**：bootstrap 一次配一个 cluster。
- **先做证据判断，再做 Skill**：首跑先发现重复候选，再读足够的代表性真实 spec 与安全反馈策略投影；Agent 输出定性建议，不用固定 0–100 分数制造精确感，不承诺成绩，不跨课比较分值。用户选中且 viability gate 通过后才建 route。
- **机会选择也是停手边界**：opportunity 写榜单后必须停；用户选号与 bootstrap viability gate 缺一不可。
- **输出按设计像人写的**：作者信号重要处有 humanize 阶段（一等公民、自带验证）；不重要处（代码/数学/MCQ）是「提交拟人」（计时/blur/focus）。
- **一作业 = 一 work dir = 一 result.json**：Stop gate 不放半成品。
- **集成边界不 mock**。

---

## 13. 「照着做出 Codex 版产品」最小蓝图

要从零造一个 Codex 版 Canvas Pilot，按此顺序：

1. **入口**：`AGENTS.md`（repo 规则 + driver 边界 + 核心产品规则 §5）。
2. **状态协议**：实现 §6 的文件读写（plan/assignments/result/_processed/REPORT）。这是产品骨架。
3. **框架技能**（`.agents/skills/`）：`canvas-setup`、`canvas-skill-opportunity`（只读证据判断→定性建议→停）、`canvas-bootstrap`（用户选中后验证并搭建）、`canvas-scan`（扫→写 plan→停）、`canvas-execute`（读批准→prepare result slots→派发→result→report）、`canvas-submit`（后续精确 mutation）、`canvas-cron`、`canvas-skip`。
4. **护栏**（`.codex/hooks/`）：`[features].hooks = true` + SessionStart / PreTool / PostTool / Stop；hook 异常可记录后 fail-open，但共享 mutation/run-state 边界必须 fail-closed。
5. **原语**（`src/`）：直接复用本仓的 `canvas_client` 等；它们 driver 无关。
6. **课程技能 + overlay**：把 §4.2/4.3/4.4 的骨架放 `.agents/skills/`，私有逻辑放 gitignored `_private/canvas-<name>-app.md`。**子任务密集阶段映射为 `.codex/agents/*.toml` 原生 subagent**（见 §8，1:1 对应 Claude 的角色，无需降级改写）。
7. **鉴权**：§10 cookie 优先 + target-exact signed mutation receipts。
8. **发布安全**：§9 三层边界 + PII 审计。

成功标准：学生首次 fork 后粘贴安装提示词，Agent 能下载仓库、先询问学校、可靠解析学校官方 Canvas 地址、通过浏览器完成鉴权，并立即展示长期 Skill 机会榜单后停在编号选择前；之后无需重新发明任何东西，就能 `scan canvas → 看计划 → 批准 → 拿草稿/提交 → 看 REPORT.md`，且能继续在 Codex 里开发本产品。

---

## 14. 当前验收证据（2026-07-18）

- 全仓回归：`432 passed, 2 skipped`。
- 全新隔离自托管 Canvas：setup → opportunity stop、enriched scan → approval
  stop、execute → report/ledger/final drafts 均通过。
- 草稿路径：generic、test-first code、PDF annotation、B1-B2 essay、五题
  quantitative PDF 均生成实质产物并通过各自验证；未授权项保持未提交。
- mutation 路径：一个普通 assignment 的后续 `submit N` 完成一次写入与
  Canvas 读回，重复 receipt 被拒；一个 Classic Quiz 的后续 `take quiz N`
  完成四份独立仲裁证据、paced actions、单次 complete 与读回，未授权 retake
  未发生。
- crash/retry 路径：批准项旧 `result.json` 被确定性归档，更新后的真实 spec
  会重新派发；同 marker resume 幂等，含糊双文件状态 fail-closed。
- 独立性：另一个没有 `.claude/` 目录、没有旧 `runs/` 的 fresh workspace
  成功完成真实只读 scan；命令轨迹没有 `.claude` / `CLAUDE_*` 调用。

这些证据验证的是合成课程与隔离 Canvas，不冒充真实学校 SSO/Duo、真实
zyBooks/GradeScope/LockDown 或真实课程提交的证明；这些边界仍需在具体用户环境
按 setup、overlay 与明确授权验证。

## 15. 维护

改动以下任一项时同步本文：`.codex/` 或 `.claude/` 的 hook/skill 注册；scan/execute plan schema；`result.json` schema；dispatch 路由表；urgent/report/delivery 行为；公开/私有边界；driver 战略。每次大改更新文首「状态」日期。
