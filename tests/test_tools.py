"""Unit tests for pytest-output parsing in sri_agent.tools.

These cover the pure parser and formatter — the logic most likely to break — without
invoking the SDK or running a real subprocess.
"""

import asyncio

from sri_agent.tools import (
    MAX_FAILURES_SHOWN,
    build_run_tests_tool,
    format_summary,
    summarize_pytest_output,
)


def test_all_passed():
    out = "..... [100%]\n5 passed in 0.42s\n"
    summary = summarize_pytest_output(0, out, "")
    assert summary.ok is True
    assert summary.passed == 5
    assert summary.failed == 0
    assert summary.duration_s == 0.42
    assert summary.failures == []


def test_some_failed_collects_failure_ids():
    out = (
        "FAILED tests/test_a.py::test_one - AssertionError: nope\n"
        "FAILED tests/test_b.py::test_two - ValueError: bad\n"
        "2 failed, 3 passed in 1.10s\n"
    )
    summary = summarize_pytest_output(1, out, "")
    assert summary.ok is False
    assert summary.passed == 3
    assert summary.failed == 2
    assert len(summary.failures) == 2
    assert "tests/test_a.py::test_one" in summary.failures[0]


def test_errors_are_counted_and_collected():
    out = "ERROR tests/test_c.py - ImportError: boom\n1 error in 0.05s\n"
    summary = summarize_pytest_output(1, out, "")
    assert summary.errors == 1
    assert any(item.startswith("ERROR") for item in summary.failures)


def test_no_tests_collected_is_a_note_not_failure():
    summary = summarize_pytest_output(5, "no tests ran in 0.01s\n", "")
    assert summary.ok is False
    assert summary.failed == 0
    assert "No tests were collected." in summary.note


def test_skipped_counted():
    summary = summarize_pytest_output(0, "3 passed, 2 skipped in 0.20s\n", "")
    assert summary.passed == 3
    assert summary.skipped == 2


def test_format_summary_headlines_pass_and_fail():
    passed = summarize_pytest_output(0, "1 passed in 0.01s\n", "")
    assert format_summary(passed).startswith("PASS:")
    failed = summarize_pytest_output(1, "1 failed in 0.01s\n", "")
    assert format_summary(failed).startswith("FAIL:")


def test_format_summary_truncates_failure_list():
    lines = "\n".join(
        f"FAILED tests/test_x.py::test_{i} - E" for i in range(MAX_FAILURES_SHOWN + 3)
    )
    out = f"{lines}\n{MAX_FAILURES_SHOWN + 3} failed in 0.5s\n"
    text = format_summary(summarize_pytest_output(1, out, ""))
    assert "...and 3 more." in text


def _tool_text(result: dict) -> str:
    return result["content"][0]["text"]


def test_run_tests_tool_runs_real_suite(tmp_path):
    # A throwaway repo with one passing and one failing test.
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_demo.py").write_text(
        "def test_ok():\n    assert 1 + 1 == 2\n\n\ndef test_bad():\n    assert 1 == 2\n"
    )
    run_tests = build_run_tests_tool(str(tmp_path), timeout_s=30)
    result = asyncio.run(run_tests.handler({}))
    text = _tool_text(result)
    assert text.startswith("FAIL:")
    assert "passed=1" in text
    assert "failed=1" in text


def test_run_tests_tool_rejects_option_injection(tmp_path):
    run_tests = build_run_tests_tool(str(tmp_path), timeout_s=30)
    result = asyncio.run(run_tests.handler({"test_path": "-x"}))
    assert result.get("is_error") is True
    assert "must not start with '-'" in _tool_text(result)
