# Per-course Skill 设计

本文件是 Canvas Pilot 四个 generic per-course skill 的**设计契约**。它告诉 fork 用户怎么读这四个 SKILL.md、每个 skill 该期望什么、以及怎么写本机的 personal design 文件把 generic skill 适配到自己具体的课。

如果你在写一个新的 generic skill（第五种重复作业），本文件就是你 follow 的模板。

---

## 共享 pipeline 模型

一个真实作业是**一序列不同步骤**，每步要求的能力不一样。"写 5 页回应论文"不是一个 prompt；它是 research → outline → draft → humanize → verify。每步有自己的成功标准、自己的定制旋钮（knob）。

Canvas Pilot 里每个 generic per-course skill 因此都是 **named stage 的 pipeline**。Pipeline 在公共 `SKILL.md` 里描述。每个 stage 独立可检视、可替换、可调。学校 / instructor 特定的旋钮在用户本机的 **personal course design** 文件里。

### 通用 SKILL.md 五段结构

每个 per-course skill SKILL.md 都遵循这五段结构：

1. **Identity & contract（身份和契约）**。这个 skill 处理什么类型的课。它的 trigger 是什么（来自 `canvas-execute` 的哪个 routing skill）。它的成功标准（draft / submitted / skipped / error）。它**显式不处理**什么。

   §1 段还必须写明该 skill 的**停止条件 baseline**：skill 服务的是**学生**，不是 instructor —— 它**永不**因为 instructor 写了"不能用 AI"或"不许合作"这种行为规则就拒绝某个作业。skill 只在 **4 类 intrinsic can't-do** 时停：(1) 物理不可能（in-person、Lockdown Browser、纸质提交），(2) 必须本人（当面签字、ID 认证、oral defense），(3) 输入缺失且无法获取（spec 哪儿都找不到；引用文件 fetch 不到且学生也给不了），(4) verification 重试后仍 fail。对于物理够不到但学生能帮忙拿到的资源（视频链接、密码保护下载、外部站登录），skill **软停**：主动 offer 学生提供 URL 或凭证，给了就继续，不给就跳这步、继续做能做的部分。skill 用 voice register 的地方（写作 skill、quiz 答题写作等），依据必须是**学生身份对齐**——学生自己的声音，不是 skill 为应付作业摆的姿态。

2. **Stage 0 —— 加载 personal course design**。每个 skill 的第一步都是读 `_private/canvas-<name>-app.md`（一个 generic skill 一个平铺 .md 文件，文件里多课共存）。它根据当前 dispatch 的 assignment 找到 `## Course {course_id}` 块，再在块内找命名 regex 匹配的 `#### {kind}` 子块。三种 fallback：
   - **整个 design 文件不存在** → dispatch 给 `canvas-bootstrap` 跑侦探，回来再继续。
   - **文件存在但本课的 Course 块缺失**（用户配了别的课但没 bootstrap 这门）→ 同上。
   - **Course 块存在但没 kind 子块匹配本次 assignment** → 单点问用户本次必需的最小参数集，append 一个新 kind 子块，继续。
   Design 文件跨 run 累积。

3. **N 个 stages**。每个 stage 一个短小节：input 是什么、output 是什么、消费 personal course design 的哪些字段、output 写到 `runs/<today>/<assignment>/<stage>/` 哪里。

4. **Personal course design schema**。一张参考表，列出 skill 尊重的每个旋钮。Required / optional / "Canvas 首跑推断"。每个旋钮一行描述加 worked demo 里的样例值。

5. **Worked demo**。给某个虚构课程（例："Code Course A — Python 1, Spring 2026, Dr. Example"）的完整 `canvas-<skill>-app.md` 示例。Fork 用户**复制粘贴改改**就行，不用从零写。

---

## 五个 generic skill

写作课作业被拆成两个 skill —— `canvas-reading-annotation`（PDF 标注）和 `canvas-essay`（长论文）—— 由 `src/ac_eng_router.py` 的 deterministic 6 层 cascade 路由。完整设计在每个 skill 的 SKILL.md 里；本 doc 按 4 个"主要"课程类别列出，写作课算一个条目，但 generic skill 的实际数量是 **5 个**。

下面每个子节指定一个 generic skill 的 **pipeline stages** 和 **knobs**。实际的 SKILL.md 用 prose 详述每个 stage；本文件是索引。

### `canvas-ics33` —— 代码课

**课程类型**：spec 住在 Canvas 之外（instructor 自有网站 / 附 PDF / 引用的教科书章节 / starter repo 的 README）、交付物是代码（**任何语言**——Python / Java / JS/TS / Rust / Go / C/C++ ——framework 语言中立）、判分通过 test 或 bundle re-clone 的编程作业。同一份 9-stage prose 跨语言通用，**只有 overlay 的命令字符串**（`test_runner`、`coverage_command`、`bundle_command`）变。

**Pipeline stages (9)：**

| # | Stage | Output |
|---|---|---|
| 1 | `fetch-spec` | `spec.md` —— 按 overlay 的 `spec_source` 抓真规格（external_site / front_page_link / attached_pdf / canvas_description / starter_readme）|
| 2 | `fetch-references` | `references/` —— spec 引用的上游材料（"from our lecture on X"）按 `reference_fetch_patterns` 正则抓全。PostToolUse hook `check-spec-grounding.py` 阻断 spec 触发 pattern 但 `references/` 为空 |
| 3 | `download-scaffold` | `repo/` —— starter 按 overlay 的 `scaffold_distribution`（git_bundle / zip_url / github_classroom / inline_in_spec / none）拉 |
| 4 | `constraints-checklist` | `constraints.md` —— 一行一个 yes/no testable 命题：硬 rubric / 数值限制 / 禁用项 / 必需 identifier / spec 给的 I/O 例子 |
| 5 | `test-first implement` | `repo/tests/` + `repo/<source>` —— 增量实现，每 stage 后跑 overlay 的 `test_runner`，达到 `coverage_target` |
| 6 | `process_humanize` | overlay 的 `process_severity != off` 时改写 git 历史——backdated commits + overlay 描述的 register（`commit_message_register`、`few_shot_examples`）。**代码课的 humanize 等价**，跟 canvas-reading-annotation 的文字 humanize 平行 |
| 7 | `audit` | `verification.log` —— Ratchet 1+2+3（数值约束实测）+ Ratchet 5（`check-identifier-grounding.py` 多语言 regex 校验 identifier 溯源）+ 测试/覆盖率检查。`pre_submit_reviewer_for` 列出的高 stakes 作业额外调 `pre-submit-reviewer` agent |
| 8 | `bundle + re-clone verify` | `draft/` —— 按 `submission_format` 打包（git_bundle / zip / single_file / online_text_entry / gradescope）。Re-clone 到临时目录 + 跑测一遍，FAIL → status: error |
| 9 | `submit` | Canvas submission 经 `canvas_submit_origin.upload_and_submit_files_with_view` wrapper（pre-gate `AlreadySubmitted` 短路 + post-verify）。`check-presubmit-audit.py` PreToolUse hook 拒绝 `verification.log` 有任何 FAIL 的上传。Headless cron 模式下（overlay `cron_env_var` env 设置），verify FAIL → status: error 不 fallback draft_ready |

**Personal course design 旋钮（course-level + per-kind sub-block）：**

| 旋钮 | 必需 | 例 |
|---|---|---|
| `course_id` | yes | `12345` |
| `language` | yes | `python`（也：`java` / `js` / `ts` / `rust` / `go` / `c` / `cpp`）|
| `language_version` | optional | `3.11` |
| `naming_regex` | yes | `^Project (?P<project_num>\d+)$` |
| `spec_source` | yes | `external_site` / `front_page_link` / `attached_pdf` / `canvas_description` / `starter_readme` |
| `spec_url_base` | conditional | `https://www.example.edu/~prof/cs101/` |
| `spec_url_template` | conditional | `{base}/projects/{project_num}/` |
| `reference_fetch_patterns` | optional | regex 列表 |
| `reference_resolver` | conditional | `{spec_base}/Notes/<match>/` |
| `scaffold_distribution` | yes | `git_bundle` \| `zip_url` \| `github_classroom` \| `inline_in_spec` \| `none` |
| `scaffold_url_template` | conditional | `{base}/projects/{project_num}/{project_num}.git` |
| `test_runner` | yes | `python -m unittest discover tests -v` |
| `coverage_command` | optional | `python -m coverage run --branch ...` |
| `coverage_target` | optional, default `none` | `100% line + branch` |
| `submission_format` | yes | `git_bundle` \| `zip` \| `single_file` \| `online_text_entry` \| `gradescope` |
| `bundle_command` | conditional | `echo Y \| python prepare_submission.py` |
| `process_severity` | yes | `off` \| `low` \| `medium` \| `high` |
| `process_humanize_config` | conditional（`process_severity != off` 时必填）| spread_days / commits_per_session / commit_message_register / few_shot_examples |
| `auto_submit_scope` | optional, default `ask-each-scan` | `Project N: confirmed` |
| `pre_submit_reviewer_for` | optional, default `(无)` | `Projects, midterms, finals` |
| `cron_env_var` | optional | env var 名（如 `ICS33_CRON_RUN`），设置则 skill 进 headless 模式 |

### `canvas-reading-annotation` —— 写作课

**课程类型**：交付物是学生 voice register 散文的作业——阅读注释、摘要写作、回应论文、扫描手写 worksheet。作者署名信号重要，所以本 skill 是 humanize stage 权重最高的那个。

**Pipeline stages：**

| # | Stage | Output |
|---|---|---|
| 1 | `classify` | `kind.txt` —— 阅读注释 / 视频习题 / 回应论文 / 课内 |
| 2 | `research` | `notes/` —— 阅读和往课内容提取上下文 |
| 3 | `outline` | `outline.md` —— 论点 / 论证结构 / originality 检查日志 |
| 4 | `draft` | `draft.md` —— 目标 voice register 全文 |
| 5 | `humanize` | `draft.final.md` —— 撑过常见 AI 检测器的输出 |
| 6 | `verify` | `verification.log` —— 长度 / 结构 / voice / detector pass |
| 7 | `export` | `output.pdf` 或 `output.docx`（按 spec）|
| 8 | `submit` | Canvas submission record（auto-submit 授权下）|

**Personal course design 旋钮：**

| 旋钮 | 必需 | 例 |
|---|---|---|
| `course_id(s)` | yes | `[12345, 12346]`（main + lab section）|
| `homework_module_id` | yes | `67890` |
| `readings_folder_path` | yes | `Files/Readings/` |
| `reading_files` | yes | `{ "Reading 1": "file_id_111", ... }` |
| `color_rubric` | optional | `{vocab: green, content: pink}` |
| `voice_register` | yes | `B1-B2, L1 hint: Chinese` |
| `rubric_text` | yes | instructor 原话 |
| `video_to_worksheet_map` | optional | `{ "Academic Verbs": "https://..." }` |
| `humanize_target_detectors` | optional, default modern set | `[gpt-zero, turnitin-ai]` |
| `auto_submit_scope` | optional, default 无 | `weekly HW Scan: confirmed` |

### `canvas-zybooks` —— zyBook-backed 数学 / 离散课

**课程类型**：用 zyBooks 作教材平台的数学 / 离散课。Spec 要么是 Canvas description 表（书面作业），要么是附 PDF（take-home exam）。交付物是解出的题目渲染成 LaTeX PDF，手动上传到 GradeScope。

**Pipeline stages：**

| # | Stage | Output |
|---|---|---|
| 1 | `classify` | `kind.txt` —— written-homework / take-home-exam / reading-completion |
| 2 | `fetch-spec` | `spec.md` —— Canvas table 解析 或 exam PDF 文本抽 |
| 3 | `fetch-exercises` | `exercises.json` —— zyBook API 拉相关章节的响应 |
| 4 | `solve` | `solutions.md` —— 每道一解，符合 instructor 必需符号约定 |
| 5 | `render-latex-pdf` | `output.pdf` —— MathJax 渲染，可 review |
| 6 | `verify` | `verification.log` —— 子题数、占位符无泄漏、LaTeX 渲染成功 |
| 7 | `draft-only` | `draft/` 镜像 —— GradeScope 上传**手动**，永不 auto |

**Personal course design 旋钮：**

| 旋钮 | 必需 | 例 |
|---|---|---|
| `canvas_course_id` | yes | `12345` |
| `zybook_course_code` | yes | `SCHOOL&COURSE2026` |
| `jwt_path` | yes | `.zybooks_localstorage.json` |
| `course_context_primer` | yes | `布尔逻辑、谓词、集合、关系、图` |
| `instructor_notation_rules` | yes | `每步引用法则要 name；一步一法则` |
| `assignment_naming_scheme` | yes | `Homework N \| Take-Home Exam N \| Reading Week N` |
| `latex_config` | optional | `{ font: helvetica, mathjax: v3 }` |

### `canvas-inside` —— Canvas 在线 quiz

**课程类型**：限时开放的 Canvas quiz，交付物是窗口内提交的答案序列。作者署名信号不重要（答案是 MCQ / 短答），但 submission-pattern 信号重要——配速、计时、focus 事件。

跟其他 generic skill 不同，**canvas-inside 的 submission-pattern humanness 实现为 framework 按名调用的 Python helper**，**不是** overlay 可配置旋钮。Overlay 配置授权哪些 quiz 自动跑 + instructor framing primer；它**不**配置 timing 分布或 event 模式。

**Pipeline (13 sections / 9 logical stages)：**

| # | Stage | Output |
|---|---|---|
| 1 | `classify` | `kind.txt` —— full quiz / single-question-video-quiz / unknown（按 `question_count` + `time_limit` + description 启发）|
| 2 | `safety gates` | early-exit 决策：`CANVAS_QUIZ_AUTORUN` env / human-hours 窗口 / per-cron 速率 / 课程白名单 |
| 3 | `reading-discovery` | `readings/` + `.txt` 抽 —— 4 层 hunt：section module → 课程文件 + syllabus → PDF 抽取 → web 搜索兜底 |
| 4 | `study-notes` | `study_notes.md` —— central thesis / 关键论点 / names 表 / 大概率出现的题 / 置信度；preface 含 overlay 的 `instructor_framework_primer` |
| 5 | `4-agent arbitration` | `final_answers.json` + `agent_passes/agent_<a\|b\|c\|d>.json` —— 4 个并行 agent 用不同 priming（notes-first / grep-first / framework-aware / contrarian）；2-2 split 手动仲裁。**Layer 1 enforcement** 在 submit 时校验 `agent_passes/` 含 ≥4 distinct JSON 文件 |
| 6 | `paced-submit` | `answer_log.json` —— 每题答 + events 按正确顺序发出（`question_viewed` → 可能 `page_blurred`+`page_focused` → 可能 `question_flagged` → 答 → `question_answered`）。Drive `src.quiz_pacing.compute_answer_schedule()` + `build_answer_sequence()` + `src.quiz_focus_events.pick_blur_slots()` + 可选 `src.quiz_strategic_miss.maybe_flip_answers()` |
| 7 | `complete` | Canvas `/complete` API 调用 `cv.complete_quiz_submission` —— 触发 Layer 1 evidence 校验 |
| 8 | `score-check` | `submission.json` 含 `kept_score` |
| 9 | `retake-with-feedback` | 可选 attempt 2（Canvas 暴露正确答案则 feedback-driven，否则 rearbitration）。**Layer 2 Stop hook** 阻断 session-stop 当 `kept_score/points_possible < 0.95` 且仍有 attempt 且 `scoring_policy == keep_highest` |

**三层独立 enforcement**（不可选、不可 overlay 配）：

| Layer | 位置 | 阻断 |
|---|---|---|
| **Layer 1** | `src/canvas_client.py:_require_canonical_arbitration_evidence` | `complete_quiz_submission` 和 `answer_quiz_questions` raise 除非 `agent_passes/` 含 ≥4 distinct JSON 文件 |
| **Layer 2** | `.claude/hooks/check-router-complete.py` Stop hook | session-stop 阻断当 quiz `status=submitted` 且 `ratio < 0.95` + `keep_highest` + 仍有 attempt |
| **Layer 3** | `.claude/hooks/_lib.py:_validate_quiz_submitted_schema` | quiz `result.json` `status=submitted` 要求 `agent_passes_count >= 4` + canonical 数值字段 + `human_ness_diagnostics.views_paired_with_answers == true` |
| schema | `.claude/hooks/check-no-runner-script.py` | 写 `runs/**/_*.py` / `run.py` 在 write-time 被阻——防 one-off 绕过脚本 |

**Personal course design 旋钮（overlay 只配课程特定数据，不配 humanness）：**

| 旋钮 | 必需 | 例 |
|---|---|---|
| `whitelisted_course_ids` | yes | `[12345]` |
| `course_name` | yes | `Intro Quiz Course` |
| `instructor_framework_primer` | yes | 自由文本散文 ≤2 页 —— §5 study_notes preface 和 §7b Agent 3 priming 都用 |
| `expected_canonical_knowledge` | optional | canonical refs 列表 —— §7b Agent 2 grep-first priming 用 |
| `auto_take_scope` | yes | `weekly Section Quiz: confirmed` |
| `human_hours_window` | optional, default `"9-22"` | `"9-22"`（PT 小时数）|
| `max_per_run` | optional, default `1` | `1` |
| `strategic_miss_default` | optional, default `off` | `off` / `on` —— 文档化课程推荐；env `CANVAS_QUIZ_STRATEGIC_MISS` 控制 runtime |
| `target_score_band` | optional, default `"92-98"` | `"92-98"` |
| `pass_band_for_retake` | optional, default `0.95` | `0.95` |

---

## Fork 用户怎么写 personal course design

预期上手流程**不是**"读这份 doc，然后手写一份 markdown"。是：

1. Fork 用户在 Claude Code 里跑 `canvas-setup`。Canvas Pilot 检测到没配置，问 Canvas URL，驱动一次浏览器登录，probe 用户的活跃课程。
2. `canvas-bootstrap` 跑**侦探**而不是采访。**它一次只设计一门课（或一门课里的一个 cluster）—— scope-first，每次跑都拿到一个 tangible deliverable，而不是 batch 扫所有课。** 对每门用户选追踪的课，按这个顺序读：**syllabus body**（instructor 写"这门课怎么运作"的总图）→ **course front page** → **modules 树** → **最近几个 assignment 的样本 description**。
3. 侦探用 `src/recurring_patterns.py` 的 `bucket_recurring(min_freq=4)` 把作业按命名 pattern 归纳——出现 4 次是 "instructor 不是临时起意" 的最低判断阈值。对每个 ≥4 簇，侦探推断：路由到 4 个 generic skill 哪一个、spec 在哪、submission 格式、作业命名 regex。
4. 侦探给学生看 **每门课一份摘要**，含所有推断的簇路由，请学生 confirm 或单点修正。Canvas 自己能答的字段全部静默推断，只在确认时打断学生。
5. Bootstrap 把确认的路由写到：
   - `_private/canvas-<generic-skill>-app.md` —— 每门路由到该 skill 的课一个 `## Course {id}` 块，块内每个 ≥4 簇一个 `#### {kind}` 子块。
   - `_private/courses.yaml` —— `routes:` 表把 course_id 映射到 generic skill 名（单 skill 课）或一组 `naming_regex → skill` 对（多 skill 课）。
6. 之后扫描和 dispatch 真实作业就"自然跑"——generic skill 在 Stage 0 读自己的 design overlay，按命名 regex 匹配到对应 `#### {kind}` 子块，按 pipeline 走。如果遇到侦探没见过的新作业 kind，skill 当场问一次，append 新的 kind 子块。

如果 fork 用户之后想调某个 stage（例：换 `canvas-reading-annotation` 的 humanize 策略，或给 `canvas-zybooks` 加一条课程特定符号规则），他直接编辑 design 文件。**没有 GUI；design 文件就是 source of truth。**

如果某个 generic skill 遇到 design 文件没 cover 的情况（例：作业命名 pattern regex 没匹配），skill 问用户**一次**，把解决方案写回 design 文件，继续。Design 文件跨 run 累积解决方案；**第一天不需要写完整**。

### Design overlay 文件 schema

每个 generic skill 读**恰好一个文件**：`_private/canvas-<skill>-app.md`。多门路由到同一 skill 的课都住在这个文件里，每门一个 `## Course {id}` 块。每个课程块里，每个 ≥4 次簇一个 `#### {kind}` 子块。

一个 worked example，fork 用户的 `canvas-ics33` 课同时有两种重复作业 (`Project N` 和 `Set N Problem M`)：

```markdown
# canvas-ics33 — Personal Course Design

This file holds per-course overlays for the canvas-ics33 skill.

## Course 12345 — CS 101: Intro to Programming

- Instructor: Dr. Example
- Auto-submit default: ask each scan

### Assignment kinds (≥4 occurrences)

#### Project N
- Naming regex: `^Project (?P<n>\d+)$`
- Occurrences detected at bootstrap: 4
- Spec location: https://www.example.edu/~prof/cs101/projects/{n}/
- Submission format: zip
- Scaffold distribution: git_bundle at {spec_url}/scaffold.git
- Auto-submit for this kind: ask each scan

#### Set N Problem M
- Naming regex: `^Set (?P<n>\d+) Problem (?P<m>\d+)$`
- Occurrences detected at bootstrap: 21
- Spec location: https://www.example.edu/~prof/cs101/exercises/set{n}/p{m}.html
- Submission format: online_text_entry
- Scaffold distribution: inline_in_spec
- Auto-submit for this kind: yes (type-level authorization)
```

如果同一 fork 用户后来加另一门同样路由到 `canvas-ics33` 的课（另一位老师的 CS 201），bootstrap 追加一个新的 `## Course 67890 — CS 201: …` 块到**同一文件**里。Generic skill 在 Stage 0 按 `course_id` 选对的块。

每个 kind 子块**独立可改**。学生改一节不打扰其他；bootstrap 重跑只替换那门课的块。

---

## 怎么加第五个 generic skill

如果你想让 Canvas Pilot 处理第五种重复作业（例：实验报告、讨论帖、演讲 + 幻灯片），路径：

1. **画 pipeline，命名 stages**。每个 stage 必须独立可测——如果你说不清单个 stage 的 input / output 契约（一句话），再拆。
2. **写 SKILL.md** 按本文件顶部的五段结构。包含 worked demo。
3. **更新 `canvas-bootstrap`** 让它识别新作业类，问对应新旋钮的访谈问题。
4. **更新 `canvas-execute`** 让 dispatch 表把新 routing skill 名映射到你的新 SKILL.md。
5. **在 README 表加一行，在 NORTH_STAR 的 "四个 generic skill" section 加一节**（现在变五个）。
6. **在 `docs/example_designs/` 里 ship 一个 worked demo overlay**，让 fork 用户有模板可抄。

欢迎 PR，但先开 issue 讨论该作业类——我们不想 ship 没人需要的 skill。
