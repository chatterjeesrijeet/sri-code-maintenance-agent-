"""Claude Agent SDK wiring: system prompt, options, permissions, and streaming.

This module owns everything about *how* the agent is configured and how a single
conversational turn is streamed and logged. The CLI (``cli.py``) owns argument
parsing and the interactive loop and calls into here.
"""

from __future__ import annotations

import asyncio
import logging

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import McpSdkServerConfig, ToolPermissionContext

from .tools import RUN_TESTS_TOOL_ID, SERVER_NAME

logger = logging.getLogger("sri_agent")

# The behavioral contract for the agent (spec §6).
SYSTEM_PROMPT = """\
You are a cautious code-maintenance assistant working inside a single target Python
repository (your working directory). Your job is to answer questions about the repo
and perform small, reviewable maintenance tasks: docstrings, missing unit tests, and
README sections.

Operating rules:
- Only read and modify files within your working directory. Never touch anything outside it.
- Read and understand the relevant code before proposing any change.
- Make the smallest change that satisfies the request, and explain what you changed and why.
- After changing code, run the `run_tests` tool and report the results honestly, including
  any failures you introduced.
- If a request is ambiguous or its scope is unclear, ask one clarifying question instead of
  guessing.
- You are a v1 maintenance assistant: decline requests to build large features, refactor
  broadly, or work outside this repository.
"""

# Built-in tools the agent may use. Reads are safe; writes/Bash are gated by the
# permission callback below. The custom run_tests tool is namespaced by the SDK.
_READ_ONLY_TOOLS = ["Read", "Grep", "Glob"]
_WRITE_TOOLS = ["Write", "Edit", "Bash"]
ALLOWED_TOOLS = [*_READ_ONLY_TOOLS, *_WRITE_TOOLS, RUN_TESTS_TOOL_ID]

# Tools that never need a permission prompt: read-only navigation plus our own
# bounded test runner (subprocess + timeout).
_AUTO_ALLOWED = {*_READ_ONLY_TOOLS, RUN_TESTS_TOOL_ID}


def build_agent_options(
    repo_path: str,
    test_server: McpSdkServerConfig,
    allow_writes: bool = False,
    model: str | None = None,
    max_turns: int = 20,
) -> ClaudeAgentOptions:
    """Assemble :class:`ClaudeAgentOptions` for a session against ``repo_path``.

    ``allow_writes`` switches the permission mode from ask-before-write
    (``"default"``) to auto-accept edits (``"acceptEdits"``); it never enables
    ``"bypassPermissions"``.
    """
    return ClaudeAgentOptions(
        cwd=repo_path,
        system_prompt=SYSTEM_PROMPT,
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="acceptEdits" if allow_writes else "default",
        mcp_servers={SERVER_NAME: test_server},
        max_turns=max_turns,
        model=model,
        can_use_tool=make_permission_callback(allow_writes),
    )


def make_permission_callback(allow_writes: bool):
    """Build the ``can_use_tool`` callback that enforces human-in-the-loop writes.

    Read-only and ``run_tests`` calls are always allowed. When ``allow_writes`` is
    set, writes are auto-approved; otherwise the user is prompted per call and may
    decline.
    """

    async def can_use_tool(
        tool_name: str, tool_input: dict, context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name in _AUTO_ALLOWED:
            return PermissionResultAllow()
        if allow_writes:
            logger.info("auto-approved (writes enabled): %s", tool_name)
            return PermissionResultAllow()

        approved = await asyncio.to_thread(_prompt_for_permission, tool_name, tool_input)
        if approved:
            return PermissionResultAllow()
        return PermissionResultDeny(message="User declined this action.")

    return can_use_tool


def _prompt_for_permission(tool_name: str, tool_input: dict) -> bool:
    """Ask the user to approve a single tool call. Returns True to allow.

    Runs in a worker thread (via ``asyncio.to_thread``) so the blocking ``input``
    call does not stall the event loop.
    """
    detail = _summarize_tool_input(tool_name, tool_input)
    print(f"\n[permission] {tool_name} wants to run: {detail}")
    answer = input("Allow? [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Produce a short, human-readable description of a pending tool call."""
    if tool_name in ("Write", "Edit"):
        return f"edit {tool_input.get('file_path', '<unknown file>')}"
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        return f"$ {command[:120]}" + ("…" if len(command) > 120 else "")
    return str(tool_input)[:160]


async def stream_agent_turn(client: ClaudeSDKClient, user_input: str) -> None:
    """Send one user turn and stream the response, logging tool calls and usage.

    Assistant text is printed to stdout as it arrives; tool invocations and the
    end-of-turn token/cost totals are logged (to stderr) for observability.
    """
    await client.query(user_input)
    print("Agent: ", end="", flush=True)

    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text, end="", flush=True)
                elif isinstance(block, ToolUseBlock):
                    logger.info(
                        "tool → %s %s", block.name, _summarize_tool_input(block.name, block.input)
                    )
        elif isinstance(message, ResultMessage):
            print()  # end the streamed line
            _log_usage(message)


def _log_usage(result: ResultMessage) -> None:
    """Log token usage and cost for a completed turn, tolerant of missing fields."""
    usage = result.usage or {}
    inp = usage.get("input_tokens", "?")
    out = usage.get("output_tokens", "?")
    cost = result.total_cost_usd
    cost_str = f"${cost:.4f}" if isinstance(cost, (int, float)) else "n/a"
    logger.info(
        "turn complete: input_tokens=%s output_tokens=%s cost=%s turns=%s",
        inp,
        out,
        cost_str,
        result.num_turns,
    )
