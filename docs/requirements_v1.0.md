# sri-code-maintenance-agent — Project Specification (v1)

> Purpose of this document: a precise, buildable spec for a first AI agent built on the
> **Claude Agent SDK** (Python). It is written to be handed to Claude Code as guidance and to
> live in the repo (e.g. as `CLAUDE.md` or `docs/SPEC.md`) so the agent-under-construction has
> its own context. Read it top to bottom before writing code.

---

## 1. Problem statement

Developers waste time on low-judgment, high-friction repo maintenance: writing docstrings,
filling test gaps, and keeping the README in sync with the code. This project is a
**command-line agent that operates on a target Python repository** to answer questions about it
and perform small, reviewable maintenance tasks under human-controlled permissions.

It is deliberately *not novel*. The value is that it is useful to any developer and that it
exercises the core of the Claude Agent SDK: the agent loop, built-in file/shell tools, one
custom tool, permission control, and a conversational session.

## 2. Goals and non-goals

**Goals (v1)**
- Point the agent at a target repo directory and hold a conversation about it.
- Answer questions about the codebase (structure, where something is defined, what a module does).
- Perform maintenance tasks on request: add/improve docstrings, write missing unit tests,
  create or update a README section.
- Run the target repo's test suite via a **custom tool** and report pass/fail back into the loop.
- Enforce human-in-the-loop permissions before any file write or shell command.
- Persist context within a single run (session), so follow-ups don't re-explain the repo.

**Non-goals (explicitly deferred — do NOT build these in v1)**
- Subagents (security/perf reviewers). *v2.*
- Hooks (pre/post-tool automation). *v2.*
- Skills/plugins, slash commands. *v3.*
- Web UI, multi-repo support, autonomous/unattended runs, CI integration. *Later.*
- Any support for languages other than Python. *Later.*

If Claude Code proposes any non-goal item, decline it. Scope creep is the main failure mode for a
first agent.

## 3. Functional requirements

1. **CLI entry point.** `sri-agent --repo <path> [--allow-writes] [--model <name>]`.
   - `--repo` (required): path to the target repository. The agent's working directory is set to this path.
   - `--allow-writes` (optional flag): switches permission mode from ask-before-write to auto-accept edits. Off by default.
   - Starts an interactive prompt loop in the terminal; user types requests, agent responds; `exit`/`quit` ends the session.
2. **Codebase Q&A.** The agent can read, search, and navigate the target repo using built-in tools and answer questions grounded in the actual files.
3. **Maintenance actions.** On request, the agent can edit/create files (docstrings, tests, README). Every write must go through the permission mechanism (see §5) unless `--allow-writes` is set.
4. **Custom tool: `run_tests`.** A Python function exposed to the agent that runs the target repo's test suite (`pytest` by default) in a subprocess and returns a structured pass/fail summary (counts, first N failures). The agent uses this to verify its own changes.
5. **Session memory.** Within one CLI run, the conversation retains context across turns. A new run starts fresh (no cross-run persistence required in v1).
6. **Graceful failure.** Missing repo path, no test runner, SDK/auth errors, and tool errors must produce a clear message, not a stack trace dump.

## 4. Technical requirements

- **Language/runtime:** Python 3.12+ (SDK requires 3.10+).
- **Packaging:** `uv` + `pyproject.toml`. Single dependency to start: `claude-agent-sdk`.
  Add `pytest` as a dev dependency for your own tests.
- **Do NOT install `claude-code-sdk`** — it is deprecated. Use `claude-agent-sdk`.
- **SDK primitive:** use `ClaudeSDKClient` (not the one-shot `query()`), because v1 needs a custom
  tool and an ongoing conversation. `query()` starts fresh each call with no memory.
- **Configuration** via `ClaudeAgentOptions` (note: snake_case fields):
  - `cwd` = the target repo path.
  - `system_prompt` = defines the agent as a cautious repo-maintenance assistant (see §6).
  - `allowed_tools` = `["Read", "Grep", "Glob", "Bash", "Write", "Edit"]` plus the custom tool.
  - `permission_mode` = `"default"` normally; `"acceptEdits"` when `--allow-writes` is passed.
    Never default to `"bypassPermissions"`.
  - `mcp_servers` = the in-process server holding the `run_tests` custom tool.
  - `max_turns` = a sane cap (e.g. 20) so a runaway loop can't burn tokens indefinitely.
- **Custom tool implementation:** use the `@tool` decorator + `create_sdk_mcp_server(...)` to run
  an in-process MCP server. No separate process.
- **Auth:** `ANTHROPIC_API_KEY` env var, or an existing Claude Code session. Document both in the README.

## 5. Safety and permissions (treat as hard requirements)

- Default behavior asks the user before any file write or shell command.
- The target repo (`--repo`) must be a *separate* directory from this agent's own source. The CLI
  should refuse (or loudly warn) if `--repo` points at the agent's own directory.
- Before making edits, the agent should check whether the target repo's git tree is dirty and warn
  if uncommitted changes exist, so the user can distinguish agent changes from their own.
- The `run_tests` tool must run in a subprocess with a timeout; never `shell=True` on
  untrusted-string input.

## 6. System prompt (behavioral contract for the agent)

The agent's system prompt must establish that it:
- Only operates within the target repo (`cwd`).
- Reads and understands relevant code before proposing changes.
- Makes the smallest change that satisfies the request and explains what it changed and why.
- Runs `run_tests` after code changes and reports results honestly, including failures it caused.
- Asks a clarifying question when a request is ambiguous rather than guessing at scope.

## 7. Proposed file layout

```
sri-code-maintenance-agent/
├── pyproject.toml
├── README.md
├── CLAUDE.md                 # this spec (or a pointer to it)
├── src/
│   └── sri_agent/
│       ├── __init__.py
│       ├── cli.py            # arg parsing + interactive loop
│       ├── agent.py          # ClaudeSDKClient setup, options, system prompt
│       ├── tools.py          # run_tests custom tool + MCP server
│       └── safety.py         # repo-path checks, git-dirty check
├── tests/
│   └── test_tools.py         # your own unit tests (e.g. run_tests parsing)
└── evals/
    └── cases.md              # small eval set (see §9)
```

## 8. Build order (milestones — review each before moving on)

1. **Skeleton.** `uv init`, `pyproject.toml`, install `claude-agent-sdk`, empty package, a CLI that parses `--repo` and prints it. Confirm it runs.
2. **Read-only agent.** `ClaudeSDKClient` with `allowed_tools` limited to `Read/Grep/Glob`, `permission_mode="default"`, interactive loop. Ask it questions about a throwaway target repo. No writes yet.
3. **Add writes under permission.** Add `Write/Edit/Bash`, wire the `--allow-writes` flag to `permission_mode`. Test a docstring edit and confirm the permission prompt behaves.
4. **Custom `run_tests` tool.** Implement with `@tool` + `create_sdk_mcp_server`, register in `mcp_servers`. Confirm the agent calls it and reports results.
5. **Safety layer.** Same-dir refusal, git-dirty warning, tool timeout.
6. **Evals + logging.** Add the eval cases (§9) and basic run logging/tracing (§10).
7. **README.** Install steps, auth, usage, safety notes.

Do not let Claude Code jump ahead. Build one milestone, read the diff, understand it, commit, then continue.

## 9. Evaluation (the enterprise habit — do not skip)

Create `evals/cases.md` with 5–10 concrete cases and expected behavior, e.g.:
- "Where is function X defined?" → returns correct file/line.
- "Add a docstring to function Y." → edits only Y, docstring is accurate, tests still pass.
- "Write a test for module Z." → creates a test that actually runs and passes.
- Ambiguous request → agent asks a clarifying question instead of guessing.
- Request outside the repo scope → agent declines.

Run these manually before every meaningful change. This is what separates an agent you can trust
from a demo.

## 10. Observability

Wire minimal tracing so you can see the agent's tool calls and token/cost per run. LangSmith has a
native Claude Agent SDK integration; a single setup call plus env vars is enough for v1. At
minimum, log each tool invocation and the final token usage to the terminal.

## 11. Acceptance criteria (v1 is "done" when)

- `sri-agent --repo <throwaway>` starts an interactive session and answers a factual question about that repo correctly.
- With writes allowed, it adds a correct docstring to a chosen function and the change is minimal.
- It can write a passing unit test for a simple function in the target repo.
- `run_tests` is invoked by the agent and its pass/fail summary is reported back accurately.
- It refuses to operate on its own source directory and warns on a dirty git tree.
- All items in `evals/cases.md` pass on a manual run.
- README lets a stranger install, authenticate, and run it without asking you questions.

## 12. How to guide Claude Code with this spec

- Paste or reference this file at the start and tell it: build in the milestone order in §8, one milestone at a time, and stop after each for review.
- Instruct it to explain each file it writes and to not implement any §2 non-goal.
- After each milestone: read the diff, ask it to justify any choice you don't understand, run the code yourself, then commit. If you can't explain a file, you haven't finished that milestone.
