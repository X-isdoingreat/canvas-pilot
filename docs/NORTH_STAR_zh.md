# Canvas Pilot —— 北极星

这份文档是 "Canvas Pilot 想成为什么" 这个问题的耐久答案。README 描述今天的产品表面，本文件描述产品的演进轨迹。

如果你是个 fork 用户，正在决定是否投入时间学这个项目，先读这份——它告诉你现在有哪些已稳定、哪些还在 roadmap 上。

如果你在框架内部工作，本文件是 "什么算真功能 vs 临时方案" 的唯一真相来源。

---

## Canvas Pilot 是什么

Canvas Pilot 是一个**通用工具产品（turnkey product）**，面向**作业有大量重复结构的学生**（每周阅读、每周题集、每周 quiz、每周与教材平台绑定的作业）。它扫你的 Canvas，规划这一周，把每个重复性作业 dispatch 到一个 course-specific skill，由该 skill 生成草稿——你 review 后才提交。

这个产品**不是**"帮我交作业"工具，也**不是**"每个 fork 用户都得自己写一遍 per-course 逻辑"的研究框架。它更接近：**给学校用的 iCal + 一个早就知道每周这四种重复作业怎么做的助手**。

Canvas Pilot 首发版一级支持的四种重复作业：

1. **代码课** —— spec 在 instructor 自己的网站，交付物是代码（默认 Python，框架是语言形态无关的）。
2. **写作课** —— 学术英语、阅读注释、摘要写作、回应论文、长论文——交付物是 prose（标注 PDF 或 DOCX）。
3. **zyBook-backed 数学 / 离散课** —— spec 是练习引用的表格，交付物是渲染成 PDF 的解答。
4. **Canvas 在线 quiz** —— 限时开放的 quiz，交付物是一序列在窗口内提交的答案。

每种重复作业映射到 **generic skill**（在 `.claude/skills/canvas-<name>/SKILL.md`），通过平铺覆盖文件 `_private/canvas-<name>-app.md` 配置成自己的具体课。**写作课特殊：拆成两个 skill** —— `canvas-reading-annotation`（PDF 标注 pipeline）+ `canvas-essay`（长论文 pipeline）—— 两个 pipeline 几乎不共享机制。`src/ac_eng_router.py` 通过 deterministic 6 层 cascade 路由每个 assignment 到对应一个。总共 **5 个 generic skill**，对应 4 种重复作业。

---

## 设计原则

这些原则**跨版本不变**。下面所有 roadmap 都遵循这些原则。

### Skill 是 pipeline 不是单体

真正的作业不是 "一个 prompt 生成一个 output"。真正的作业有不同的阶段，每段需要的能力不一样。写 5 页论文是 research → outline → draft → humanize → verify，不是单一函数。每个 stage 都**独立可调、可换、可检视**。Personal design 文件定制单个 stage，不是整个 skill。

### 审批 gate 是 filesystem 边界

`canvas-scan` 写出 `plan.json` 后停下。`canvas-execute` 在用户回复 approval 后读它。两个 skill，两次 Skill-tool 调用——用户可以在中间打断。Prose 指令无法强制这条；filesystem state 可以。

### 默认出草稿，提交需要 standing authorization

默认行为：出草稿，你手动上传。Auto-submit 是 per-skill / per-overlay 的，要 verification log 通过才能调上传 API。Auto-submit 永远不是 silent default。

### Agent 停在 can't-do，不是 shouldn't-do

Per-course skill 服务的是**学生**。skill 永不因为 instructor 写了行为规则（"不能用 AI"、"不许合作"、"不许改述"）就拒绝某个作业；用这个 framework 跑某个作业是不是符合 operator 所在学校的政策，是 **operator 本人**的决定，跟下面"Academic-integrity arbitration"非范围条款一致。

skill **只在物理上没法继续**时才停。4 类 intrinsic can't-do：(1) 物理不可能（in-person 到场、Lockdown Browser、纸质提交、当面签字），(2) 必须本人（academic honesty contract 签字、ID 认证、oral defense），(3) 输入缺失且无法获取（spec 哪儿都找不到、引用文件 fetch 不到且学生也给不了），(4) verification 重试后仍 fail。

对于物理够不到但靠学生帮忙可能拿到的资源——视频链接、密码保护下载、外部站登录——skill **软停**：主动 offer 学生提供 URL 或凭证，给了就继续，不给就跳这一步、做能做的部分。

skill 用 voice register 的地方（比如"按 B1-B2 国际生语风写"），依据是**学生身份对齐**——学生选这种语风因为他本身就是那个英语水平。Register 是学生自己的声音，不是 skill 为了应付作业摆的姿态。产出质量关切（要扛得过内容质量审查）是单独的 stage 关切，由下面 humanize stage 处理。

**scope-first onboarding**：`canvas-bootstrap` **一次只设计一门课（或一门课里的一个 cluster）**——学生每次跑都拿到一个 tangible deliverable，而不是 batch 处理所有课再丢一墙文字。

### 产出看起来像人写的，by design

对作者署名信号重要的作业（写作课、长回答），pipeline 包含一个专门的 **humanize stage**，唯一任务是把草稿做成能撑过当前 AI 内容检测器的输出。这是个 first-class stage 带自己的 verification，不是脚注。v0.1 在 `canvas-reading-annotation`（写作）里 ship 这个 stage——失败代价最高那里。

对作者署名信号不重要的作业（代码、数学解、MCQ 答案），等价关切是**提交模式（submission-pattern）的人性化**——配速、计时、focus / blur 事件——在 submission stage 处理，不在内容 stage。

### 一个 assignment = 一个 work directory = 一个 result.json

Stop hook 拒绝释放 session 直到每个 dispatched assignment 都产生了合法 result。没有静默的 partial completion。

### `assignment.description` 很少是真规格

Per-course skill 把 Canvas description 当作 routing hint，从 instructor 网站、附 PDF、module 页面或引用的阅读材料拉真实指令。具体哪门课的 spec 住在哪里，写在那门课的 personal design 文件里。

### Integration boundary 上不用 mock

对 Canvas 的测试用录制的 fixture 或 sandbox 课程；mock 抓不到 spec 和真实 API 之间的 drift。

---

## 五个 generic skill

每个 ship 的 skill 都是 **N-stage pipeline** 结构。Pipeline 在公共 `SKILL.md` 里描述。学校 / instructor 特定的单 stage 定制住在用户的 `_private/canvas-<name>-app.md`。

### `canvas-ics33` —— 代码课

```
fetch-spec → fetch-references → download-scaffold → constraints-checklist →
test-first implement → process_humanize（process-graded 课启用）→
audit（identifier-grounding + 数值约束 + coverage 检查）→
bundle + re-clone verify → submit（auto-submit 授权下）
```

Framework **语言中立**——overlay 指定该语言的 test runner / build 命令 / submission 格式。同一份 9-stage prose 驱动 Python+unittest+git-bundle 课或 Java+gradle+jar 课，只有 overlay 的命令字符串不同。

`process_humanize` 是 first-class stage，跟 `canvas-reading-annotation` 的文字 humanize 平行：对 process-graded 课（grader 看 git log），把 commit 历史重写成多 commit、backdated、undergrad-message-register 的序列。默认不启用；overlay 的 `process_severity` 控制。

Personal design 指定：course id、language + test runner / coverage 命令 / submission 格式、instructor 的 spec URL pattern、scaffold 分发机制（git bundle / zip / GitHub Classroom / inline / none）、reference-fetch 正则、process_humanize 旋钮（spread 天数 / commit message register / few-shot 示例）、auto-submit 范围、headless cron env var 名。

### `canvas-reading-annotation` —— 写作课（PDF 标注）

```
classify（reading_annotation / video_exercises / in_class_skip / ...）→
locate_reading（按 overlay 的 reading_files 表）→
extract_text_and_blanks（PyMuPDF 按 y 坐标 group underscore）→
annotate_pdf（在原页就地加 color 高亮 + margin notes）→
fill_answer_blanks（typed 答案 ≥90% 行宽，按 voice register）→
verify（6-check gate：line fill / note 密度 / 色系 / 页数 /
        no 重叠 / no sticky icons）→ submit（auto-submit 授权下）
```

Personal design 指定：course id(s)、homework module id、reading 文件 mapping、color rubric（vocab 色系 vs content 色系）、voice register（自由文本描述学生语风）、instructor rubric verbatim、视频→worksheet 配对。

### `canvas-essay` —— 写作课（长论文）

```
load_persona（MBTI 推导出语气向量）→
parse_spec（扫附 PDF / module 页 / 外链）→
load_sample_essays（few-shot anchor）→
generate（outline → body → revise）→
figure_captions + works_cited（3 层 cascade）→
verify（字数 ≥ spec 下限 / 引用数 / figure caption 数）→
output（.docx / .pdf 按 overlay）→ submit（auto-submit 授权下）
```

Personal design 指定：essay 名称 trigger pattern（被 `src/ac_eng_router.py` 用作 Layer 2 信号）、voice register 细则、sample essay 文件路径、citation style（MLA / APA / Chicago）、figure caption 格式、persona 推导模板。

### `canvas-zybooks` —— zyBook-backed 数学 / 离散课

```
classify（书面作业 / take-home exam / 阅读完成）→
fetch-spec（Canvas description table 或 attached PDF）→
fetch-exercises（zyBook API）→ solve → render-LaTeX-PDF →
verify（子题数 / 占位符无泄漏）→
draft-only（GradeScope 上传手动）
```

Personal design 指定：Canvas course id、zyBook course code、JWT 路径、solver 的 course-context primer、instructor 特定符号规则（例："每步引用的法则要 name；一步一法则"）、作业命名规范。

### `canvas-inside` —— Canvas 在线 quiz

```
classify（full quiz / 单题视频 quiz / 未知）→
4 safety gates（autorun / human-hours / per-cron 速率 / whitelist）→
reading 发现（4-layer hunt：module → files+syllabus → PDF → web）→
study_notes.md → 4-agent arbitration（notes-first / grep-first /
framework-aware / contrarian）→ paced-submit（humanness：timing、blur/
focus、sequence non-linearity、optional strategic miss）→ complete →
score-check → retake-with-feedback（Layer 2 gated）
```

Submission-pattern humanness 实现为 SKILL.md 按名调用的 Python helper，不是 overlay 可配置旋钮：`src.quiz_pacing.compute_answer_schedule`（log-normal per-question timing，78% 时长利用率，outlier 注入）、`src.quiz_pacing.build_answer_sequence`（skip-ahead pass + revisit pass）、`src.quiz_focus_events.pick_blur_slots` / `pick_flagged_questions`（page_blurred/focused pairs + question_flagged 事件）、`src.quiz_strategic_miss.maybe_flip_answers`（可选，env-gated）。Framework prose 按精确名引用。

**三层独立 enforcement** 防 4-agent arbitration 被绕过：
1. `src.canvas_client._require_canonical_arbitration_evidence`——`complete_quiz_submission` 和 `answer_quiz_questions` API 拒绝调用除非 `runs/<work>/agent_passes/` 含 ≥4 个 distinct JSON 文件。
2. `.claude/hooks/check-router-complete.py` Stop hook——当 `kept_score/points_possible < 0.95` 且仍有 attempt 且 `scoring_policy == keep_highest` 时阻断 session stop，强制 retake。
3. `.claude/hooks/_lib.py:_validate_quiz_submitted_schema`——拒绝任何 `status: submitted` 但缺 `agent_passes_count >= 4`、缺 canonical 数值字段、或 `human_ness_diagnostics.views_paired_with_answers != true` 的 quiz `result.json`。

Personal design 指定：白名单 course ids、instructor framework primer（散文）、预期 canonical 知识、auto-take scope、human-hours window、max-per-run、strategic-miss 默认、target-score-band、retake-pass-band。

---

## Roadmap

### v0.1 —— 第一次公开发布

Ship：
- 五个框架 skill（`canvas-setup` / `canvas-bootstrap` / `canvas-scan` / `canvas-execute` / `canvas-skip`）——全部跑通，经过真实 fork 测试。
- 四个 generic per-course skill 作为**功能性 pipeline**，每个有上面列举的 stages。Humanize stage 在 `canvas-reading-annotation` 已存在。Submission-pattern 人性化在 `canvas-inside` 已存在。
- 每个 skill 一个 worked demo personal design 文件，在 `docs/SKILL_DESIGN.md` 记录。
- Playwright 的 cookie auth 作为唯一支持的 auth path。
- 五个框架 skill 的 Codex sidecar mirror。

显式**不**包含：
- Token-mode auth（有些学校禁用；cookie 在每个用 Canvas 的学校都能用，所以只 ship cookie）。
- Web UI。所有交互通过这个目录下的 Claude Code。
- 对新课自动检测该用哪个 generic skill。用户在 bootstrap 时选。

### v0.2 —— 稳健性 pass

- Humanize stage 推广到适用的所有四个 skill（写作 / quiz 文字回答），不只是写作课。
- Canvas API flaky 时的 retry 策略（Canvas 不稳定；v0.1 让错误向上传播，v0.2 区分 transient vs terminal）。
- pipeline 部分失败的更好失败消息（例：humanize stage verification 失败但草稿本身可以）。

### v0.5 —— 多学校可移植性

- `_examples/` 加第二个学校的 worked example（fork 用户贡献的第二个学校代码课 overlay；merge 前我们 verify 跑通端到端）。
- Personal design schema 稳定下来，作为契约文档化。

### v1.0 —— 生产可用 turnkey

- 五个 generic skill 鲁棒到任何在美国 Canvas 学校的 fork 用户跑 `canvas-setup`、答 ~3 个问题，本周的重复作业就出草稿，不用写定制 prose。
- Verification gate 严到可以为低风险 assignment 类型 ship opt-in auto-submit。

---

## 显式**不在**范围内

- **替代 Claude Code**。这是 Claude Code 项目，不是独立 CLI。产品依赖 CC 的 skill dispatch、tool use、approval 语义。试图剥离 CC 会做出更差的产品和不可维护的框架。
- **支持 Canvas 之外的 LMS**。每个 LMS 都有足够 API 表面，支持两个等于维护两套框架。Canvas 已经够广；v1.0 目标是 "Canvas 上做得好"，不是 "三个 LMS 都凑合"。
- **多租户 SaaS**。Canvas Pilot 是 per-user 本地安装。多租户引入我们不想吸收的 auth / payment / abuse 向量。想要 SaaS 自己 fork 自己 host。
- **手搓 detector-bypass 遥测**。Humanize stage 是 pipeline 里的一个 stage，不是研究项目。我们 ship 对当前 detector 有效的方法，detector 更新时跟更。我们**不发表** "如何绕过 detector X" 指南；那些工作在 stage 内部存在。
- **学术诚信判定**。这工具对某门课用着合不合适，是 operator 看学校政策自己决定的。框架在这件事上意见中立，**不 ship policy-screening 逻辑**。

---

## 这份文件怎么更新

当某个真实 ship 版本到达上面某个里程碑，对应的 v0.x / v1.0 section 就地改为过去时（"v0.1 shipped 2026-MM-DD, scope as described"）。当前版本下面的 roadmap section 保持前瞻式描述。

当某个 generic skill 的 stage 形态实质变化（新 stage 加入、旧 stage 撤销、stage contract 改变），"五个 generic skill" section 更新，对应 SKILL.md 的 changelog 加一行。

**这份文件是契约。skill 是实现。它们分歧时，本文件正确，skill 是 bug。**
