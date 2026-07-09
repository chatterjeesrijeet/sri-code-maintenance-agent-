---
name: milestone-review
description: >-
  Pre-commit gate for this project's milestone-driven build (spec §8). Use before proposing a
  commit or moving to the next milestone: it maps the current work to the milestone's acceptance
  criteria (§11), checks the non-goals weren't violated, and confirms tests/evals were run. Run
  it whenever the user says "let's commit", "next milestone", or "are we done with this step".
---

# Milestone review — build discipline gate

This project is built **one milestone at a time** (spec §8). "Vibe-coding ahead" is the main
failure mode. Before any commit or milestone hand-off, walk this checklist and report a concise
PASS/CONCERN summary. Do not commit for the user unless they ask.

## Step 1 — Identify the current milestone

Milestones (spec §8):
1. Skeleton (`uv init`, `pyproject.toml`, `claude-agent-sdk` installed, CLI parses `--repo`).
2. Read-only agent (`ClaudeSDKClient`, `Read/Grep/Glob`, `permission_mode="default"`, loop).
3. Writes under permission (`Write/Edit/Bash`, `--allow-writes` → `acceptEdits`).
4. Custom `run_tests` tool (`@tool` + `create_sdk_mcp_server`, registered in `mcp_servers`).
5. Safety layer (same-dir refusal, git-dirty warning, subprocess timeout).
6. Evals + logging (`evals/cases.md`, tool-call + token logging).
7. README (install, auth, usage, safety).

State which milestone this diff belongs to.

## Step 2 — Scope check (did we stay in the lane?)

- [ ] The diff advances **only** the current milestone — no jumping ahead.
- [ ] No **non-goal** was built (spec §2): subagents, product hooks, skills/slash commands,
      web UI, multi-repo, autonomous runs, CI, non-Python support. Flag any drift.
- [ ] The change is the **smallest** that satisfies the milestone.

## Step 3 — Correctness & safety

- [ ] Uses `claude-agent-sdk` (not `claude-code-sdk`), `ClaudeSDKClient` (not `query()`),
      snake_case `ClaudeAgentOptions`.
- [ ] `permission_mode` never defaults to `bypassPermissions`.
- [ ] Safety invariants intact where relevant: same-dir refusal, git-dirty warning,
      `run_tests` subprocess timeout, no `shell=True` on untrusted input.
- [ ] Errors surface as clear messages, not raw tracebacks.

## Step 4 — Verification actually ran

- [ ] `uv run pytest` was run and the result is reported honestly (including new failures).
- [ ] Relevant `evals/cases.md` cases were run manually (from milestone 6 onward).
- [ ] Lint/format clean (`uv run ruff check .` / `ruff format .`).

## Step 5 — Acceptance criteria (spec §11)

Map the diff to the matching §11 bullet(s) and confirm each is met. If any is unmet, this
milestone is **not done** — say so plainly and list what's missing.

## Output

Give the user: the milestone, a PASS / CONCERNS verdict, a short bullet list of what was
verified, and any gaps. Then let them decide to commit — suggest a tight commit message but
don't run `git commit`/`git push` unless asked.
