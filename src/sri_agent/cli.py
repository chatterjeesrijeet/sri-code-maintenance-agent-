"""Command-line entry point: argument parsing, startup safety, interactive loop.

Usage:
    sri-agent --repo <path> [--allow-writes] [--model <name>]

Type requests at the prompt; ``exit`` or ``quit`` (or Ctrl-D) ends the session.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from claude_agent_sdk import ClaudeSDKClient, ClaudeSDKError

from .agent import build_agent_options, stream_agent_turn
from .safety import (
    SafetyError,
    ensure_repo_is_not_agent_source,
    git_dirty_summary,
    resolve_repo_path,
)
from .tools import DEFAULT_TEST_TIMEOUT_S, build_test_server

logger = logging.getLogger("sri_agent")

_EXIT_COMMANDS = {"exit", "quit"}


def build_parser() -> argparse.ArgumentParser:
    """Define the CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="sri-agent",
        description="Ask questions about and perform small maintenance tasks on a "
        "target Python repository, under human-controlled permissions.",
    )
    parser.add_argument("--repo", required=True, help="Path to the target repository.")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Auto-accept file edits instead of prompting before each write.",
    )
    parser.add_argument(
        "--model", default=None, help="Override the model (e.g. a Claude model id)."
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        help="Maximum agent turns per request before stopping (default: 20).",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=DEFAULT_TEST_TIMEOUT_S,
        help=f"Timeout in seconds for the run_tests tool (default: {DEFAULT_TEST_TIMEOUT_S}).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry point. Returns a process exit code."""
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)

    try:
        repo_path = resolve_repo_path(args.repo)
        ensure_repo_is_not_agent_source(repo_path)
    except SafetyError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    _warn_if_dirty(repo_path)

    test_server = build_test_server(str(repo_path), timeout_s=args.test_timeout)
    options = build_agent_options(
        repo_path=str(repo_path),
        test_server=test_server,
        allow_writes=args.allow_writes,
        model=args.model,
        max_turns=args.max_turns,
    )

    print(f"sri-agent ready. Target repo: {repo_path}")
    print(
        "Writes are "
        + ("AUTO-ACCEPTED (--allow-writes)." if args.allow_writes else "prompted per change.")
    )
    print("Type a request, or 'exit'/'quit' to leave.\n")

    try:
        asyncio.run(_run_session(options))
    except (KeyboardInterrupt, EOFError):
        print("\nGoodbye.")
    except ClaudeSDKError as exc:
        print(f"\nAgent SDK error: {exc}", file=sys.stderr)
        print(
            "Check authentication: set ANTHROPIC_API_KEY, or run `claude` once to sign in.",
            file=sys.stderr,
        )
        return 1
    return 0


async def _run_session(options) -> None:
    """Open one SDK session and run the interactive request loop."""
    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                user_input = await asyncio.to_thread(input, "you> ")
            except EOFError:
                print()  # newline after Ctrl-D
                break
            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in _EXIT_COMMANDS:
                break
            await stream_agent_turn(client, user_input)
            print()


def _warn_if_dirty(repo_path) -> None:
    """Warn the user if the target repo has uncommitted changes."""
    dirty, summary = git_dirty_summary(repo_path)
    if dirty:
        count = len(summary.splitlines())
        print(
            f"Warning: target repo has {count} uncommitted change(s). "
            "Commit or stash first so you can tell agent edits from your own.\n",
            file=sys.stderr,
        )


def _configure_logging(verbose: bool) -> None:
    """Send observability logs to stderr; keep agent output clean on stdout."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
