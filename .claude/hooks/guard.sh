#!/usr/bin/env bash
# PreToolUse guard: runs BEFORE a tool executes and can block it (exit 2).
#
#   - Write/Edit/MultiEdit: block edits to files outside this project directory,
#     so a stray path can't clobber another repo on the machine.
#   - Bash: block only destructive commands (rm -rf /, force push, hard reset).
#
# Plain `git push` is deliberately NOT blocked here — it falls through to the
# normal permission prompt, so a user-requested push works after confirmation.
set -euo pipefail

payload="$(cat)"
proj="${CLAUDE_PROJECT_DIR:-$PWD}"

field() {  # read a top-level field
  printf '%s' "$payload" | python3 -c \
    "import sys,json;print(json.load(sys.stdin).get('$1',''))" 2>/dev/null || true
}
input() { # read tool_input.<name>
  printf '%s' "$payload" | python3 -c \
    "import sys,json;print(json.load(sys.stdin).get('tool_input',{}).get('$1',''))" 2>/dev/null || true
}

tool="$(field tool_name)"

case "$tool" in
  Write|Edit|MultiEdit)
    fp="$(input file_path)"
    [ -z "$fp" ] && exit 0
    case "$fp" in /*) abs="$fp" ;; *) abs="$proj/$fp" ;; esac
    abs="$(python3 -c 'import os,sys;print(os.path.normpath(sys.argv[1]))' "$abs")"
    case "$abs" in
      "$proj"/*|"$proj") ;;  # inside the project → allow
      *) echo "Blocked: edit outside project → $abs (harness only edits $proj)." >&2; exit 2 ;;
    esac
    ;;
  Bash)
    cmd="$(input command)"
    if printf '%s' "$cmd" | grep -Eq \
      'rm[[:space:]]+-[rR]?f?[[:space:]]+/|git[[:space:]]+push[[:space:]].*(--force|-f)([[:space:]]|$)|git[[:space:]]+reset[[:space:]]+--hard'; then
      echo "Blocked destructive command: $cmd" >&2
      exit 2
    fi
    ;;
esac
exit 0
