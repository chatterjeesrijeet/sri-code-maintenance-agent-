"""Safety checks that gate the agent before it touches a target repository.

These are pure, side-effect-light helpers so they can be unit-tested without the
SDK. They enforce the hard requirements in the spec: the target repo must be a
separate tree from the agent's own source, and the user should be warned when the
target repo has uncommitted changes (so agent edits are distinguishable from their
own).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

# git status runs against local files only; a couple of seconds is plenty.
_GIT_TIMEOUT_S = 10


class SafetyError(Exception):
    """Raised when a safety precondition is violated (e.g. bad or unsafe repo path).

    The message is meant to be shown directly to the user, so keep it actionable.
    """


def agent_source_root() -> Path:
    """Return the root directory of this agent's own source tree.

    Layout is ``<root>/src/sri_agent/safety.py``, so the root is three parents up.
    """
    return Path(__file__).resolve().parents[2]


def resolve_repo_path(raw_path: str) -> Path:
    """Expand, resolve, and validate a user-supplied ``--repo`` path.

    Returns the absolute, symlink-resolved path. Raises :class:`SafetyError` with a
    clear message if the path does not exist or is not a directory.
    """
    path = Path(raw_path).expanduser().resolve()
    if not path.exists():
        raise SafetyError(f"Target repo path does not exist: {path}")
    if not path.is_dir():
        raise SafetyError(f"Target repo path is not a directory: {path}")
    return path


def ensure_repo_is_not_agent_source(repo_path: Path) -> None:
    """Refuse to operate on the agent's own source tree.

    Raises :class:`SafetyError` if ``repo_path`` is the agent's root, lives inside
    it, or contains it. Running the agent on itself risks it editing its own code
    mid-session, which the spec explicitly forbids.
    """
    agent_root = agent_source_root()
    if (
        repo_path == agent_root
        or repo_path.is_relative_to(agent_root)
        or agent_root.is_relative_to(repo_path)
    ):
        raise SafetyError(
            "Refusing to run against the agent's own source tree "
            f"({agent_root}). Point --repo at a separate repository."
        )


def is_git_repo(repo_path: Path) -> bool:
    """Return True if ``repo_path`` is inside a git working tree."""
    result = _run_git(repo_path, "rev-parse", "--is-inside-work-tree")
    return result is not None and result.returncode == 0 and result.stdout.strip() == "true"


def git_dirty_summary(repo_path: Path) -> tuple[bool, str]:
    """Report whether the target repo has uncommitted changes.

    Returns ``(is_dirty, summary)``. ``summary`` is the porcelain status text when
    dirty, or an empty string when clean. If the path is not a git repo (or git is
    unavailable), returns ``(False, "")`` — a missing git tree is not an error here,
    just nothing to warn about.
    """
    if not is_git_repo(repo_path):
        return False, ""
    result = _run_git(repo_path, "status", "--porcelain")
    if result is None or result.returncode != 0:
        return False, ""
    changes = result.stdout.strip()
    return bool(changes), changes


def _run_git(repo_path: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    """Run a git subcommand in ``repo_path`` with a timeout; never uses a shell.

    Returns the completed process, or ``None`` if git is missing or times out. We
    pass an explicit argument list (no ``shell=True``) so repo-controlled paths can
    never be interpreted as shell syntax.
    """
    try:
        return subprocess.run(
            ["git", *args],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
