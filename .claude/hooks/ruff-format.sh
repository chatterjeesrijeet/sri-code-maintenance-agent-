#!/usr/bin/env bash
# PostToolUse hook: format + lint-fix Python files after Edit/Write/MultiEdit.
#
# Reads the hook payload from stdin (JSON), pulls the edited file path out of
# tool_input.file_path, and runs ruff on it when it's a .py file. It is a
# best-effort convenience: if ruff isn't installed, or the path isn't Python,
# it exits 0 quietly and never blocks the edit.
set -euo pipefail

payload="$(cat)"

# Extract tool_input.file_path without assuming jq is present.
file_path="$(
  printf '%s' "$payload" | python3 -c \
    'import sys, json; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))' \
    2>/dev/null || true
)"

[ -z "$file_path" ] && exit 0
case "$file_path" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file_path" ] || exit 0

# Prefer the project's pinned ruff (via uv); fall back to a global ruff; else no-op.
if command -v uv >/dev/null 2>&1 && uv run ruff --version >/dev/null 2>&1; then
  RUFF=(uv run ruff)
elif command -v ruff >/dev/null 2>&1; then
  RUFF=(ruff)
else
  exit 0
fi

"${RUFF[@]}" check --fix --quiet "$file_path" >/dev/null 2>&1 || true
"${RUFF[@]}" format --quiet "$file_path" >/dev/null 2>&1 || true
exit 0
