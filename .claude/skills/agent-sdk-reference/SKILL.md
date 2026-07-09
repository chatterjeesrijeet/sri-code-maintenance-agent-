---
name: agent-sdk-reference
description: >-
  Quick reference and gotcha-list for building on the Claude Agent SDK (Python) — the exact
  primitives this project uses: ClaudeSDKClient, ClaudeAgentOptions, the @tool decorator,
  create_sdk_mcp_server, permission modes, and custom in-process MCP tools. Use BEFORE writing
  or reviewing SDK wiring in agent.py or tools.py, or when an SDK call behaves unexpectedly.
---

# Claude Agent SDK (Python) — Reference for this project

This project is built on **`claude-agent-sdk`** (Python). Consult this before writing SDK glue.
If anything here conflicts with the installed SDK, trust the SDK and update this file.

> First, get ground truth for the current model IDs, pricing, and API params: invoke the
> **`claude-api`** skill. Do not answer model/pricing questions from memory.

## Non-negotiables (these cause silent bugs)

- **Package:** `claude-agent-sdk`. **Never** `claude-code-sdk` (deprecated). Import as
  `from claude_agent_sdk import ...`.
- **Primitive:** `ClaudeSDKClient` for an ongoing session + custom tools. `query()` is one-shot
  with **no memory** — wrong for v1.
- **Options are snake_case:** `ClaudeAgentOptions(cwd=..., system_prompt=..., allowed_tools=[...],
  permission_mode=..., mcp_servers=..., max_turns=...)`.
- **Permission modes:** `"default"` (ask), `"acceptEdits"` (auto-accept edits). Never
  `"bypassPermissions"`. `--allow-writes` is the only thing that flips `default → acceptEdits`.
- **`max_turns`:** always set a sane cap (e.g. 20) so a runaway loop can't burn tokens.

## Minimal shape of the wiring

```python
from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, tool, create_sdk_mcp_server

@tool("run_tests", "Run the target repo's pytest suite and summarize pass/fail.", {"path": str})
async def run_tests(args):
    # subprocess with a TIMEOUT; never shell=True on untrusted strings.
    # return {"content": [{"type": "text", "text": summary}]}
    ...

server = create_sdk_mcp_server(name="repo-tools", version="1.0.0", tools=[run_tests])

options = ClaudeAgentOptions(
    cwd=target_repo_path,
    system_prompt=SYSTEM_PROMPT,              # cautious repo-maintenance assistant (spec §6)
    allowed_tools=["Read", "Grep", "Glob", "Bash", "Write", "Edit", "run_tests"],
    permission_mode="acceptEdits" if allow_writes else "default",
    mcp_servers={"repo-tools": server},
    max_turns=20,
)

async with ClaudeSDKClient(options=options) as client:
    await client.query(user_message)
    async for msg in client.receive_response():
        ...  # stream/print; log each tool call and final token usage
```

## Custom tools (`@tool` + `create_sdk_mcp_server`)

- Runs **in-process** — no separate process to manage.
- Tool functions are `async`. The third `@tool` arg is the input schema (a dict of name→type).
- Return the MCP content shape: `{"content": [{"type": "text", "text": "..."}]}`.
- The tool name you expose (`"run_tests"`) must appear in `allowed_tools`.

## `run_tests` implementation notes (spec §4, §5)

- Run `pytest` in a **subprocess** with a **timeout**; catch `TimeoutExpired`.
- Pass an argument list (`["pytest", "-q", ...]`), never a shell string. No `shell=True`.
- Parse stdout into a structured summary: counts + the first N failures. Keep parsing in a pure
  helper so `tests/test_tools.py` can unit-test it without invoking the SDK.
- Handle "no test runner / no tests collected" as a clean message, not an exception.

## Streaming & observability (spec §10)

- Iterate `client.receive_response()` to stream assistant output and observe tool calls.
- At minimum: log every tool invocation and the final token usage to the terminal.
- Optional for v1: LangSmith has a native Agent SDK integration (one setup call + env vars).

## Auth (spec, README)

- `ANTHROPIC_API_KEY` env var, **or** an existing Claude Code session. Document both.
- On auth failure, print a clear, actionable message — never a raw traceback.

## Common failure modes

- Importing the deprecated `claude-code-sdk` → fix the dependency.
- camelCase option names (`systemPrompt`) → use snake_case.
- Using `query()` then wondering why context is lost → switch to `ClaudeSDKClient`.
- Forgetting to add the custom tool name to `allowed_tools` → agent "can't see" the tool.
- No `max_turns` → runaway loops.
