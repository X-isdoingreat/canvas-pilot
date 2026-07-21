# Canvas Pilot Claude Code 功能总表

> ⚠️ **SUPERSEDED (2026-06-13)** → 产品架构/功能/能力映射的单一真相源现为
> [`docs/PRODUCT_SPEC.md`](./PRODUCT_SPEC.md)（含本文的 Claude→Codex 能力映射，且已更新为 Codex 主力）。
> 本文保留作 Claude driver 的功能快照历史；两者冲突以 PRODUCT_SPEC 为准。
>
> 目的：把当前 Claude Code driver 已实现的功能面一次性列清楚，作为 Codex sidecar 迁移/对照时的功能基线。
>
> 范围：记录 `.claude/settings.json`、`.claude/hooks/*`、`.claude/skills/canvas-*`、`.claude/agents/*` 的职责、触发、产物和边界。
>
> 注意：本文只描述功能与接口，不复制私有课程的详细操作手册。具体 course IDs、真实 URL、身份、文件 ID 等仍只在 `SECRETS.md` 和私有 skill 内部。

---

## 0. 一句话架构

Claude Code driver 把 Canvas 作业流水线拆成两段：

```text
canvas-scan
  -> 扫 Canvas
  -> 写 assignments.json / plan.json
  -> 给用户看 plan
  -> STOP

用户批准

canvas-execute
  -> 读 plan.json
  -> 解析批准
  -> touch .scan_in_progress
  -> dispatch 到 course-specific skills
  -> 每项写 result.json
  -> 写 REPORT.md
  -> 同步 final_drafts/
  -> 删除 .scan_in_progress
```

核心安全边界：

- scan 不 execute。
- execute 必须来自用户批准。
- 每个 assignment 必须有合法 `result.json`。
- `.scan_in_progress` 存在时，Stop hook 不允许半成品 session 结束。

---

## 1. 运行时配置

### 1.1 `.claude/settings.json`

职责：

- 注册 Claude Code plugins。
- 注册 SessionStart / PreToolUse / PostToolUse / Stop hooks。
- 用绝对 Windows 路径调用 hook 脚本。

当前 enabled plugins：

| Plugin | 用途 |
|---|---|
| `dev-browser@dev-browser-marketplace` | headless browser / browser automation |
| `claude-mem@thedotmack` | memory |
| `superpowers@superpowers-marketplace` | 通用 power-user skills |
| `ralph-loop@claude-plugins-official` | loop 模式 |
| `hookify@claude-plugins-official` | hook 辅助 |
| `code-review@claude-plugins-official` | code review |
| `pr-review-toolkit@claude-plugins-official` | PR review toolkit |
| `commit-commands@claude-plugins-official` | commit/push/PR 辅助 |
| `plugin-dev@claude-plugins-official` | plugin 开发辅助 |

### 1.2 Hook 注册表

| Event | Matcher | Hook |
|---|---|---|
| `SessionStart` | none | `.claude/hooks/inject-context.py` |
| `PreToolUse` | `Bash` | `.claude/hooks/check-presubmit-audit.py` |
| `PreToolUse` | `Bash` | `.claude/hooks/check-public-leak.py` |
| `PostToolUse` | `Write\|Edit` | `.claude/hooks/check-result-schema.py` |
| `PostToolUse` | `Write\|Edit` | `.claude/hooks/check-spec-grounding.py` |
| `PostToolUse` | `Write\|Edit` | `.claude/hooks/check-identifier-grounding.py` |
| `PostToolUse` | `Bash` | `.claude/hooks/check-bash-output.py` |
| `Stop` | none | `.claude/hooks/check-router-complete.py` |

---

## 2. 状态文件契约

| 文件 | 写入方 | 读取方 | 用途 |
|---|---|---|---|
| `runs/<today>/assignments.json` | `canvas-scan` / `src.router --dry-run` | scan / execute / Stop hook / sub-skills | 今日 pending assignment snapshot |
| `runs/<today>/plan.json` | `canvas-scan` | `canvas-execute` | 用户审批计划 |
| `runs/<today>/.scan_in_progress` | `canvas-execute` | Stop hook | execute-mode marker |
| `runs/<today>/<slug>/result.json` | sub-skill 或 execute defer path | hooks / execute / report | 单个 assignment 的完成证明 |
| `runs/<today>/REPORT.md` | `canvas-execute` | 用户 | 本轮结果汇总，顶部 urgent banner |
| `runs/<today>/todo.md` | `canvas-skip` | 用户 | 手工处理项 |
| `runs/_processed.json` | `canvas-execute` | scan / execute / context injection | 跨天去重 ledger |
| `final_drafts/` | `canvas-execute` | 用户 | 最终 draft 文件入口 |

`result.json` 合法 status：

- `draft_ready`
- `submitted`
- `skipped`
- `error`

---

## 3. 主流程 Skill：canvas-scan

路径：

```text
.claude/skills/canvas-scan/SKILL.md
```

触发：

- 用户说 `scan canvas`
- 用户说 `check canvas`
- 用户说 `what's due`
- 用户说 `do my homework`
- 用户显式 `/canvas-scan`

允许工具：

- `Bash`
- `Read`
- `Write`
- `Edit`
- `Glob`
- `Grep`
- `WebFetch`
- `TodoWrite`

职责：

1. Sanity check Canvas auth：
   ```bash
   python -m src.canvas_client --probe
   ```
2. 扫 pending：
   ```bash
   python -m src.router --dry-run
   ```
3. 写 `runs/<today>/assignments.json`。
4. 两层去重：
   - 今日 work dir 已有 terminal `result.json`。
   - `runs/_processed.json` 中已有 terminal entry。
   - `deferred_to_next_run: true` 例外，重新进入 plan。
5. 查 live Canvas submission state。
6. 按 due time 分桶：
   - `overdue`
   - `urgent`
   - `soon`
   - `later`
7. 写 `runs/<today>/plan.json`。
8. 渲染学生可读 plan 表。
9. 停止，等待用户批准。

明确禁止：

- 不调用任何 sub-skill。
- 不写 `result.json`。
- 不写 `REPORT.md`。
- 不同步 `final_drafts/`。
- 不创建 `.scan_in_progress`。
- 不处理 7-day window 外的 assignment。

关键边界：

`canvas-scan` 是 proposal 阶段。它只能提出 plan，不能行动。

---

## 4. 主流程 Skill：canvas-execute

路径：

```text
.claude/skills/canvas-execute/SKILL.md
```

触发：

用户看完 `canvas-scan` 输出的 plan 后回复：

- `approve all`
- `批准全部`
- `做 1, 3, 5`
- `只做 urgent`
- `defer N`
- `cancel`

允许工具：

- `Bash`
- `Read`
- `Write`
- `Edit`
- `Glob`
- `Grep`
- `WebFetch`
- `Skill`
- `TodoWrite`

职责：

1. 检查 `plan.json` 和 `assignments.json` 存在。
2. 检查 plan 未过期。
3. 清理旧日期 orphan `.scan_in_progress`。
4. 创建今日 marker：
   ```text
   runs/<today>/.scan_in_progress
   ```
5. 解析用户批准：
   - all
   - urgent only
   - index list
   - index range
   - swap skill
   - defer
   - cancel
6. 原子更新 `plan.json` 的 `user_decision`。
7. 对 approved items 逐个 dispatch。
8. 每个 item 读取 sub-skill 写出的 `result.json`。
9. 更新 `runs/_processed.json`。
10. context 紧张时 pause-and-ask：
    - 为未处理项写 deferred skipped `result.json`
    - 询问用户继续还是 defer
11. finalize：
    - 补齐 deferred items 的 `result.json`
    - 写 `REPORT.md`
    - 同步 `final_drafts/`
    - 删除 `.scan_in_progress`

明确禁止：

- 不重新 scan。
- 不凭空生成 plan。
- 不执行未批准项。
- 不跳过 result.json。
- 不忘记删除 marker。
- 不绕过 sub-skill inline 做作业。

关键边界：

`canvas-execute` 是唯一 dispatch skill 的地方。

---

## 5. Dispatch 表

`canvas-execute` 根据 plan item 的 `proposed_skill` / route skill dispatch：

| Route skill / proposed skill | Claude skill | 功能 |
|---|---|---|
| `code_py` / `canvas-ics33` | `.claude/skills/canvas-ics33/SKILL.md` | 代码课 / Python project & exercise |
| `ac_english` / `canvas-reading-annotation` | `.claude/skills/canvas-reading-annotation/SKILL.md` | 文档批注 / worksheet / writing draft |
| `quiz` / `canvas-inside` | `.claude/skills/canvas-inside/SKILL.md` | 授权 Canvas quiz |
| `zybooks` / `canvas-zybooks` | `.claude/skills/canvas-zybooks/SKILL.md` | zyBook-backed PDF draft |
| `mixed_unsupported` / `canvas-skip` | `.claude/skills/canvas-skip/SKILL.md` | unsupported/manual todo |

Dispatch 规则：

- 顺序执行，不并行。
- 每个 sub-skill 负责自己的 work dir。
- 每个 sub-skill 必须写 `result.json`。
- 如果 sub-skill 不存在，execute 必须停止并报错，不 inline 替代。

---

## 6. Course-Specific Skills

### 6.1 canvas-ics33

路径：

```text
.claude/skills/canvas-ics33/SKILL.md
```

用途：

- 处理 Python code course 的 projects 和 exercise sets。
- Canvas assignment description 通常不是 spec。
- 真 spec 来自外部 instructor site。

核心产物：

- `<work>/spec.md`
- `<work>/references/*`
- `<work>/REQUIREMENTS.md`
- `<work>/constraints.md`
- `<work>/repo/`
- `<work>/draft/*`
- `<work>/verification.log`
- `<work>/result.json`

核心功能：

- fetch external spec。
- fetch referenced lecture/source artifacts。
- implement code incrementally。
- run tests。
- enforce coverage / numeric / identifier grounding verification。
- create bundle or final deliverable。
- 在授权条件和 verification 通过后可 upload/submit。

关键 guardrails：

- `check-spec-grounding.py`
- `check-identifier-grounding.py`
- `check-presubmit-audit.py`
- `check-bash-output.py`
- optional `pre-submit-reviewer`

### 6.2 canvas-reading-annotation

路径：

```text
.claude/skills/canvas-reading-annotation/SKILL.md
```

用途：

- 处理 document / academic English assignment。
- 真实 instructions 通常在 module page / files folder。
- 产 typed annotated PDF / worksheet draft。

核心产物：

- `<work>/requirements.md`
- `<work>/hw_type.txt`
- `<work>/attachments/*`
- `<work>/draft/*.pdf`
- `<work>/verification.log`
- `<work>/result.json`

核心功能：

- classify assignment type：
  - reading annotation
  - video exercises
  - in-class skip
  - response paper / unsupported
- download reading or worksheet source。
- render annotated PDF。
- enforce voice / formatting / line-fill checks。
- draft-only unless explicit authorization says otherwise。

关键 guardrails：

- classification before generation。
- 写作课 verification helper。
- no AI-tell voice constraints。
- no invented worksheet structure。

### 6.3 canvas-inside

路径：

```text
.claude/skills/canvas-inside/SKILL.md
```

用途：

- 处理授权课程的 Canvas online quiz。

核心产物：

- `<work>/quiz_meta.json`
- `<work>/readings/*`
- `<work>/study_notes.md`
- `<work>/questions.json`
- `<work>/questions_simplified.json`
- `<work>/final_answers.json`
- `<work>/answer_log.json`
- `<work>/result.json`

核心功能：

- auth-mode gate。
- course whitelist。
- quiz type classification。
- study notes construction。
- multi-pass answer arbitration。
- paced answering。
- result audit diagnostics。

关键 guardrails：

- course whitelist。
- env gates for autorun/submit。
- save audit artifacts before live action。

### 6.4 canvas-zybooks

路径：

```text
.claude/skills/canvas-zybooks/SKILL.md
```

用途：

- 处理 zyBook-backed discrete math style assignments。

核心 assignment kinds：

- Written Homework
- Take-Home Exam
- Reading completion

核心产物：

- `<work>/draft/*.pdf`
- `<work>/solutions.md` or equivalent audit notes
- `<work>/result.json`

核心功能：

- classify assignment kind first。
- parse Canvas description table for graded exercises。
- fetch zyBook content。
- render typed PDF draft。
- download/annotate attached PDF for take-home exam style work。
- never upload to GradeScope / Canvas / zyBooks by default。

关键 guardrails：

- do not trust zyBook `student_view` as instructor truth。
- do not render whole sections when only graded subset is assigned。
- draft-only, user manually uploads.

### 6.5 canvas-skip

路径：

```text
.claude/skills/canvas-skip/SKILL.md
```

用途：

- 处理 unsupported/manual/in-class/deferred assignment。

核心产物：

- `runs/<today>/todo.md`
- `<work>/result.json`

核心功能：

- append manual todo。
- write `status: skipped` result。
- explain why no automation happened。

---

## 7. Hooks

### 7.1 `_lib.py`

路径：

```text
.claude/hooks/_lib.py
```

共享功能：

- `read_event()`
- `block()`
- `passthrough()`
- `safe_main`
- `today_dir()`
- `matches_result_json()`
- `validate_result_schema()`

关键点：

`safe_main` 是 hook 防 runaway 的安全网。内部异常必须 fail-open 并写 `hook-errors.log`，避免 Claude 被 hook bug 卡死。

### 7.2 inject-context.py

Event：

```text
SessionStart
```

功能：

- 读今日 `assignments.json`。
- 读 `runs/_processed.json`。
- 注入 pending / ledger 摘要。
- 给 Claude 新 session 提供项目状态。

### 7.3 check-presubmit-audit.py

Event：

```text
PreToolUse(Bash)
```

触发：

- Bash command 包含 submit/upload/quiz submit 相关模式。

功能：

- 定位 work dir。
- 要求 `verification.log` 存在。
- 要求至少一条 PASS。
- 要求没有 FAIL。
- 不满足则 block。

### 7.4 check-public-leak.py

Event：

```text
PreToolUse(Bash)
```

触发：

- git add / commit / push 等。

功能：

- 防止 private-only path 推到 public upstream。
- 扫描 forbidden content markers。
- 区分 origin/private 和 upstream/public。
- `git push upstream` 时强防御。

### 7.5 check-result-schema.py

Event：

```text
PostToolUse(Write|Edit)
```

触发：

- 写或改 `runs/**/result.json`。

功能：

- 校验 JSON。
- 校验 status enum。
- `draft_ready` 要求 `draft_path` 存在。
- `submitted` 要求 audit trail。

### 7.6 check-spec-grounding.py

Event：

```text
PostToolUse(Write|Edit)
```

触发：

- `result.json` status 是 `draft_ready` 或 `submitted`。
- work dir 有 `spec.md`。

功能：

- 如果 spec 提到 external/class/lecture/provided references，而 `references/` 空，则 block。

### 7.7 check-identifier-grounding.py

Event：

```text
PostToolUse(Write|Edit)
```

触发：

- `result.json` status 是 `draft_ready` 或 `submitted`。
- draft 是 `.py` 或可解析 code-like PDF。

功能：

- 从 draft 提取 identifiers。
- 对比 `spec.md` / `references/*` / `assignments.json` / builtins。
- suspicious ungrounded identifiers 则 block。

### 7.8 check-bash-output.py

Event：

```text
PostToolUse(Bash)
```

功能：

- 拦 pytest/unittest failure。
- 拦 coverage < 100%。
- 拦特定代码课项目中未 backdate 的多 commit 模式。

### 7.9 check-router-complete.py

Event：

```text
Stop
```

功能：

- 如果没有 `.scan_in_progress`，放行。
- 如果有 marker，则读取今日 `assignments.json`。
- 要求每个 assignment 有合法 `result.json`。
- 缺失或 invalid 时 exit 2，阻止 session stop。

关键点：

这是 execute-mode 的 closeout gate。

---

## 8. Agent

### pre-submit-reviewer

路径：

```text
.claude/agents/pre-submit-reviewer.md
```

用途：

- 上传前 fresh-eye reviewer。
- 不继承主 session 合理化。
- 只看 spec / requirements / constraints / references / draft。

输入：

- `work_dir`

检查：

1. deliverable shape。
2. numeric constraints。
3. identifier grounding。
4. spec-reference completeness。
5. rubric semantic check。

输出：

```text
## Verdict: GO | GO WITH WARNINGS | BLOCK
```

并附 requirement table 和 actions before resubmit。

禁止：

- 不修改文件。
- 不信主 session notes。
- 不随意 WebFetch。
- 不放宽 numeric constraints。

---

## 9. Claude Driver 功能基线

Codex sidecar 如果要追平 Claude driver，至少要对照以下能力：

| Capability | Claude Code current status |
|---|---|
| Session start context injection | implemented |
| Scan-only plan generation | implemented |
| Approval-gated execute | implemented |
| Dispatch to course-specific skills | implemented |
| Result schema guard | implemented |
| Execute stop gate | implemented |
| Pre-submit verification gate | implemented |
| Public/private leak guard | implemented |
| Spec reference grounding | implemented |
| Identifier grounding | implemented |
| Bash test/coverage guard | implemented |
| Fresh-eye reviewer agent | implemented |
| REPORT.md urgent banner | implemented |
| Delivery folder sync | implemented |
| Cross-day processed ledger | implemented |

---

## 10. Codex Sidecar v0 对照范围

Codex v0 不需要一次性追平全部 Claude 功能。建议只对照：

| Capability | Codex v0 target |
|---|---|
| `AGENTS.md` repo entry | yes |
| scan skill skeleton | yes |
| execute skill skeleton | yes |
| skip skill skeleton | yes |
| run state schema docs | yes |
| public/private boundary docs | yes |
| hook design | yes |
| hook implementation | future |
| private course skills | no |
| pre-submit reviewer | no |
| full grounding hooks | no |

---

## 11. 维护规则

修改以下内容时需要同步本文：

- `.claude/settings.json`
- `.claude/hooks/*`
- `.claude/skills/canvas-*`
- `.claude/agents/*`
- scan/execute plan schema
- `result.json` schema
- dispatch route table
- urgent/report/delivery behavior

