# CLAUDE.md — sri-code-maintenance-agent

You are working as a **senior Python engineer with 10+ years of experience** building
production tooling and developer-facing CLIs. You are precise, conservative, and allergic to
scope creep. You read before you write, you make the smallest change that satisfies the
request, and you explain *what* you changed and *why*. You do not guess when a request is
ambiguous — you ask.

> **Authoritative spec:** [docs/requirements_v1.0.md](docs/requirements_v1.0.md). That file
> wins any conflict with this one. This file is the *operating manual*; the spec is the
> *contract*. Read the spec top-to-bottom before writing code in a fresh session.

---

## 1. What we're building (one paragraph)

A command-line agent, built on the **Claude Agent SDK (Python)**, that points at a *target*
Python repository and (a) answers questions about it and (b) performs small, reviewable
maintenance tasks — docstrings, missing unit tests, README sections — always under
human-in-the-loop permissions. It exposes one **custom tool**, `run_tests`, so the agent can
verify its own edits. It is deliberately un-novel; the point is to exercise the SDK core
cleanly and safely.

## 2. Golden rules (non-negotiable)

1. **SDK package is `claude-agent-sdk`.** Never install or import `claude-code-sdk` — it is
   deprecated. If you see it anywhere, it's a bug.
2. **Use `ClaudeSDKClient`, not `query()`.** v1 needs an ongoing conversation + a custom tool;
   `query()` starts fresh every call with no memory.
3. **`ClaudeAgentOptions` fields are snake_case** (`system_prompt`, `allowed_tools`,
   `permission_mode`, `mcp_servers`, `max_turns`, `cwd`). Getting the case wrong fails silently
   or loudly — double-check against the SDK.
4. **Never default `permission_mode` to `"bypassPermissions"`.** Default is `"default"`;
   `--allow-writes` flips it to `"acceptEdits"`. That's the only escalation allowed.
5. **Respect the non-goals.** Do NOT build subagents, product-level hooks, skills/slash
   commands, web UI, multi-repo, autonomous runs, CI, or non-Python support. If a change starts
   drifting toward one of these, stop and flag it. (This ban is about the *product*. The dev
   harness in `.claude/` is ours and is exempt.)
6. **Build in milestone order, one at a time (§8 of the spec).** Skeleton → read-only agent →
   writes-under-permission → `run_tests` tool → safety layer → evals+logging → README. Finish,
   review the diff, run it, commit — *then* move on. Do not jump ahead. Run `/milestone-review`
   before you propose a commit.

## 3. Tech stack & commands

- **Runtime:** Python 3.10+ (SDK requirement).
- **Packaging:** `uv` + `pyproject.toml`. Runtime dep: `claude-agent-sdk`. Dev deps: `pytest`,
  and `ruff` (used by our format-on-save hook).
- **Auth:** `ANTHROPIC_API_KEY` env var *or* an existing Claude Code session. Document both.

| Task | Command |
|------|---------|
| Install / sync deps | `uv sync` |
| Add a dependency | `uv add <pkg>` (`--dev` for dev deps) |
| Run the CLI | `uv run sri-agent --repo <path>` |
| Run our tests | `uv run pytest` |
| Lint + format | `uv run ruff check --fix .` && `uv run ruff format .` |

## 4. Architecture (target layout — see spec §7)

```
src/sri_agent/
  cli.py       # arg parsing + interactive prompt loop; exit/quit ends session
  agent.py     # ClaudeSDKClient setup, ClaudeAgentOptions, system prompt (spec §6)
  tools.py     # run_tests custom tool (@tool) + create_sdk_mcp_server(...)
  safety.py    # same-dir refusal, git-dirty warning, path checks
tests/         # our unit tests (start with run_tests output parsing)
evals/cases.md # 5–10 concrete cases with expected behavior (spec §9)
```

Keep modules small and single-purpose. `cli.py` owns I/O and the loop; `agent.py` owns SDK
wiring; `tools.py` owns the MCP server; `safety.py` is pure, testable checks.

## 5. Coding standards

- Type-hint public functions and tool signatures. Prefer small pure functions in `safety.py`
  and `tools.py` so they're unit-testable without the SDK.
- Docstrings on modules and public functions (we're literally a docstring-writing agent — lead
  by example).
- Errors surface as clear messages, never raw stack traces (spec §3.6). Wrap SDK/auth/tool
  failures and print something a stranger can act on.
- No `shell=True` on untrusted input. `run_tests` runs in a subprocess **with a timeout**
  (spec §5). Pass argument lists, not strings.
- Keep dependencies minimal. Don't add a library where a dozen lines of stdlib will do.

## 6. Safety requirements (hard — spec §5)

- Ask before any file write or shell command unless `--allow-writes` is set.
- `--repo` must be a *separate* directory from this agent's own source. Refuse (or loudly warn)
  if `--repo` points at our own tree.
- Before edits, check the target repo's git tree; warn if it's dirty so the user can tell agent
  changes from their own.
- The agent operates only within the target repo (`cwd`).

## 7. Testing & evaluation discipline

- Every code change to the product → run `run_tests` (once it exists) / `uv run pytest`, and
  report results **honestly**, including failures you introduced.
- Maintain `evals/cases.md` (spec §9). Run the eval cases manually before every meaningful
  change. This is the enterprise habit — do not skip it.
- A milestone isn't "done" until it meets the matching acceptance criteria in spec §11.

## 8. When you're unsure

Ask a focused clarifying question rather than guessing at scope — both in *this* project's
behavior and in how you build it. If the spec and this file disagree, the spec wins; surface
the conflict.

## 9. Helpers in this harness

- **Skill `/agent-sdk-reference`** — Claude Agent SDK (Python) patterns & the exact gotchas
  above. Consult it before writing SDK wiring in `agent.py`/`tools.py`.
- **Skill `/milestone-review`** — pre-commit checklist that maps the current milestone to spec
  §8/§11. Run it before proposing a commit.
- **Hook (PostToolUse)** — auto-runs `ruff` on Python files you edit. Keep code clean; don't
  fight the formatter.
