---
name: ag-learn
description: Improve skills from agent friction or derive steering principles from user corrections.
dependencies:
- ag-ledger
- dev.llm-session
- dev.shortcuts
- sc
version: 0.0.0
---

# ag-learn

Use this skill to turn agent mistakes, repeated friction, or useful workflow discoveries into better skills.

## Constants

- `LEARN_ROOT`: `$HOME/.llm/skills/learn`
- `LEARN_ARCHIVE`: `$HOME/.llm/skills/learn/.archive`
- `SKILL_TOKEN`: `ag-learn`

## Core Workflow

1. Identify the learning source: current session, named session, merged PR, pasted evidence, or review window.
2. For default/current-session learning, read `./references/session-forensics.md` and scan the active rollout JSONL before choosing the final learning focus.
   - Treat the user's immediate complaint as a seed, not the whole evidence boundary.
   - Include earlier same-session mistakes, interruptions, corrections, and explicit skill invocations when they are related or explain why the immediate complaint happened.
   - If the user names a narrower source such as a PR, pasted evidence, or review window, scan that source and any current-session turns that led to the request.
3. Inspect enough durable evidence to understand the friction.
   - Good evidence: transcript excerpts, rollout JSONL, PR comments, diffs, logs, generated artifacts, command output, saved learn notes.
   - If transcript forensics are needed, read `./references/session-forensics.md`.
4. Rank candidate learnings by prominence before choosing what to save or apply.
   - Prefer issues that recur across the session, required user correction, caused rework, or crossed skill boundaries.
   - Do not choose only the most recent failure unless the requested source is explicitly narrow.
   - Collapse timebound incidents into the durable workflow gap behind them. For example, "one PR had stale mergeability" should become a reusable finalization rule only if the evidence shows a general GitHub-state handling gap.
   - De-prioritize one-off environmental flakes, temporary CI behavior, and already-fixed implementation details unless they reveal a reusable skill gap.
5. Decide whether the issue should change a skill.
   - Optimize an existing skill when the workflow already has a clear home.
   - Propose a new skill when repeated work has no clean home.
   - Use `none` when the lesson is too situational or not skill-shaped.
6. Read the target skill or shortcut source before judging the gap.
   - For skill changes, follow `$sc` and edit only the canonical source tree.
   - For `trigger:<shortcut>` cases, resolve the shortcut through `$dev.shortcuts` before classifying the mistake.
7. Produce 1-3 high-signal improvements. Do not pad with weak lessons.
   - When the user asks to scan an entire conversation or session, include a short candidate-friction ranking in the saved note coverage so the selected issues are auditable.
   - If a selected improvement is already covered by an existing skill, report it as already addressed and do not create a duplicate proposed change.
8. Save a learn note only when the user asks for persistence, the finding should be reused, or the run is review/code/formal mode.
   - Before creating or updating any saved note under `LEARN_ROOT`, read `./references/templates.md`.
   - Saved notes must follow the durable note template from `templates.md`; the compact output format below is only for the user-facing summary.
   - Before reporting the saved path, verify the note contains `## Evidence Inspected`, `## Coverage`, `## Known Gaps`, at least one `## [number] Improvement Opportunity`, and `### Routing`.

## Modes

- Default/current session: use the Core Workflow, including the active rollout scan in `./references/session-forensics.md`.
- `steering`: read `./references/steering-mode.md`; inventory user directives and corrections across the current conversation, group recurring behavioral patterns, and derive reusable steering principles.
- `review [time interval] [path]`: read `./references/review-mode.md`.
- `code`: read `./references/code-mode.md`.
- Evidence-based skill optimization: use the Core Workflow to inspect evidence, rank friction, and select improvements; route canonical edits, validation, packaging, and sync through `$sc`.
- Formal saved note or durable routing: read `./references/templates.md`.
- Session lookup, parent/fork tracing, or ledger logging: read `./references/session-forensics.md` and `./references/ledger.md`; use `$ag-ledger` and `$dev.llm-session` as needed.

## Output

The compact numbered format below is for chat summaries only. Do not use it as the saved-note file format.

For each improvement, keep the user-facing summary compact:

```markdown
1. [short title]
Evidence: [durable evidence checked]
Skill gap: [what the skill should have made easier or prevented]
Target: [existing skill, proposed skill, or none]
Proposed change: [implementation-ready change, or n/a]
Promote: [yes|no]
```

When saving a note, write it under `LEARN_ROOT` with a filename containing the literal `ag-learn` token. Verify the saved path exists before reporting it.

## Archive Learning

When the user archives a learning, move it to `LEARN_ARCHIVE`.
