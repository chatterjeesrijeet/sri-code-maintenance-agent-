"""The ``run_tests`` custom tool and its in-process MCP server.

The agent uses this tool to verify its own edits by running the target repo's
pytest suite in a subprocess (with a timeout, never a shell) and getting back a
compact pass/fail summary. Output parsing lives in :func:`summarize_pytest_output`,
a pure function, so it can be unit-tested without invoking the SDK or pytest.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from dataclasses import dataclass, field

from claude_agent_sdk import create_sdk_mcp_server, tool
from claude_agent_sdk.types import McpSdkServerConfig

# The MCP server + tool names. The SDK exposes the tool to the model as
# ``mcp__<server>__<tool>``; agent.py adds this id to allowed_tools.
SERVER_NAME = "repo_tools"
TOOL_NAME = "run_tests"
RUN_TESTS_TOOL_ID = f"mcp__{SERVER_NAME}__{TOOL_NAME}"

DEFAULT_TEST_TIMEOUT_S = 120
MAX_FAILURES_SHOWN = 5

# Pytest's terminal summary counts, e.g. "3 passed", "1 failed", "2 errors".
_COUNT_RE = {
    "passed": re.compile(r"(\d+)\s+passed"),
    "failed": re.compile(r"(\d+)\s+failed"),
    "errors": re.compile(r"(\d+)\s+errors?"),
    "skipped": re.compile(r"(\d+)\s+skipped"),
}
_DURATION_RE = re.compile(r"in\s+([\d.]+)s")


@dataclass
class TestSummary:
    """Structured result of a pytest run."""

    ok: bool
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    duration_s: float | None = None
    failures: list[str] = field(default_factory=list)
    note: str = ""


def summarize_pytest_output(returncode: int, stdout: str, stderr: str) -> TestSummary:
    """Parse pytest's textual output into a :class:`TestSummary`.

    Pure and deterministic — no I/O. ``ok`` is true only when pytest exits 0.
    Exit code 5 (no tests collected) is reported as a note rather than a failure.
    """
    text = f"{stdout}\n{stderr}"

    counts = {key: _first_int(pattern, text) for key, pattern in _COUNT_RE.items()}
    duration_match = _DURATION_RE.search(text)
    duration = float(duration_match.group(1)) if duration_match else None

    # Collect the individual failing/erroring test ids pytest prints, e.g.
    # "FAILED tests/test_x.py::test_y - AssertionError: ...".
    failures = [
        line.strip() for line in text.splitlines() if line.startswith(("FAILED ", "ERROR "))
    ]

    note = ""
    if returncode == 5:
        note = "No tests were collected."
    elif returncode not in (0, 1) and not failures:
        # Non-standard exit (usage error, internal error) with nothing parsed.
        note = f"pytest exited with code {returncode}."

    return TestSummary(
        ok=returncode == 0,
        passed=counts["passed"],
        failed=counts["failed"],
        errors=counts["errors"],
        skipped=counts["skipped"],
        duration_s=duration,
        failures=failures,
        note=note,
    )


def format_summary(summary: TestSummary) -> str:
    """Render a :class:`TestSummary` as a short, agent-readable report."""
    headline = "PASS" if summary.ok else "FAIL"
    parts = [
        f"passed={summary.passed}",
        f"failed={summary.failed}",
        f"errors={summary.errors}",
        f"skipped={summary.skipped}",
    ]
    if summary.duration_s is not None:
        parts.append(f"time={summary.duration_s}s")
    lines = [f"{headline}: " + ", ".join(parts)]

    if summary.failures:
        shown = summary.failures[:MAX_FAILURES_SHOWN]
        lines.append(f"First {len(shown)} failure(s):")
        lines.extend(f"  - {item}" for item in shown)
        if len(summary.failures) > MAX_FAILURES_SHOWN:
            lines.append(f"  ...and {len(summary.failures) - MAX_FAILURES_SHOWN} more.")
    if summary.note:
        lines.append(summary.note)
    return "\n".join(lines)


def build_run_tests_tool(repo_path: str, timeout_s: int = DEFAULT_TEST_TIMEOUT_S):
    """Build the ``run_tests`` SDK tool bound to ``repo_path``.

    Kept separate from :func:`build_test_server` so the tool's ``handler`` can be
    unit-tested directly. Binding the repo path here (rather than trusting a
    model-supplied path) scopes test execution to the target repo; ``test_path`` is
    an optional narrowing argument the model may pass to run a subset of tests.
    """

    @tool(
        TOOL_NAME,
        "Run the target repository's pytest suite and return a pass/fail summary. "
        "Optionally pass 'test_path' (a file or node id, relative to the repo) to "
        "run a subset. Use this after making code changes to verify them.",
        {"test_path": str},
    )
    async def run_tests(args: dict) -> dict:
        test_path = (args.get("test_path") or "").strip()

        # Reject option-injection: a value like "-x" would become a pytest flag.
        if test_path.startswith("-"):
            return _error(f"Invalid test_path {test_path!r}: must not start with '-'.")

        command = ["python", "-m", "pytest", "-q"]
        if test_path:
            command.append(test_path)

        try:
            completed = await asyncio.to_thread(
                subprocess.run,
                command,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return _error(f"run_tests timed out after {timeout_s}s.")
        except FileNotFoundError:
            return _error("Could not run pytest (is Python/pytest available in the repo env?).")

        summary = summarize_pytest_output(completed.returncode, completed.stdout, completed.stderr)
        return {"content": [{"type": "text", "text": format_summary(summary)}]}

    return run_tests


def build_test_server(
    repo_path: str, timeout_s: int = DEFAULT_TEST_TIMEOUT_S
) -> McpSdkServerConfig:
    """Create the in-process MCP server exposing ``run_tests`` for ``repo_path``."""
    tool_impl = build_run_tests_tool(repo_path, timeout_s)
    return create_sdk_mcp_server(name=SERVER_NAME, version="1.0.0", tools=[tool_impl])


def _first_int(pattern: re.Pattern[str], text: str) -> int:
    """Return the first integer captured by ``pattern`` in ``text``, or 0."""
    match = pattern.search(text)
    return int(match.group(1)) if match else 0


def _error(message: str) -> dict:
    """Build an MCP error result the agent will see as a failed tool call."""
    return {"content": [{"type": "text", "text": message}], "is_error": True}
