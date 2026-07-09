"""Unit tests for the safety layer in sri_agent.safety."""

import subprocess

import pytest

from sri_agent.safety import (
    SafetyError,
    agent_source_root,
    ensure_repo_is_not_agent_source,
    git_dirty_summary,
    is_git_repo,
    resolve_repo_path,
)


def test_resolve_missing_path_raises(tmp_path):
    missing = tmp_path / "does-not-exist"
    with pytest.raises(SafetyError, match="does not exist"):
        resolve_repo_path(str(missing))


def test_resolve_file_is_not_a_directory(tmp_path):
    file_path = tmp_path / "a.txt"
    file_path.write_text("x")
    with pytest.raises(SafetyError, match="not a directory"):
        resolve_repo_path(str(file_path))


def test_resolve_valid_directory(tmp_path):
    assert resolve_repo_path(str(tmp_path)) == tmp_path.resolve()


def test_refuses_agent_source_root():
    with pytest.raises(SafetyError, match="own source tree"):
        ensure_repo_is_not_agent_source(agent_source_root())


def test_refuses_directory_inside_agent_source():
    inside = agent_source_root() / "src"
    with pytest.raises(SafetyError):
        ensure_repo_is_not_agent_source(inside)


def test_allows_unrelated_directory(tmp_path):
    # A separate temp dir is fine — no exception.
    ensure_repo_is_not_agent_source(tmp_path.resolve())


def test_non_git_directory_is_not_dirty(tmp_path):
    assert is_git_repo(tmp_path) is False
    assert git_dirty_summary(tmp_path) == (False, "")


def test_git_dirty_detects_uncommitted_change(tmp_path):
    _init_git_repo(tmp_path)
    (tmp_path / "new.txt").write_text("hello")
    dirty, summary = git_dirty_summary(tmp_path)
    assert dirty is True
    assert "new.txt" in summary


def test_git_clean_repo_reports_clean(tmp_path):
    _init_git_repo(tmp_path)
    dirty, summary = git_dirty_summary(tmp_path)
    assert dirty is False
    assert summary == ""


def _init_git_repo(path):
    """Initialize a committed git repo in ``path`` for dirty/clean tests."""
    env = {"GIT_TERMINAL_PROMPT": "0"}
    run = lambda *a: subprocess.run(  # noqa: E731 - tiny local helper
        ["git", *a],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        env={**_base_env(), **env},
    )
    run("init")
    run("config", "user.email", "t@example.com")
    run("config", "user.name", "Test")
    (path / "README.md").write_text("init")
    run("add", "-A")
    run("commit", "-m", "initial")


def _base_env():
    import os

    return dict(os.environ)
