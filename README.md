# sri-code-maintenance-agent

A command-line agent, built on the [Claude Agent SDK](https://docs.claude.com/en/api/agent-sdk/overview),
that points at a **target Python repository** and helps you maintain it: answer questions about
the code, add or improve docstrings, write missing unit tests, and update README sections —
always under human-controlled permissions.

It runs the target repo's test suite through a custom `run_tests` tool so it can verify its own
changes, and it keeps context across a conversation within a single run.

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for dependency management
- Authentication for the Claude Agent SDK (see below)

## Install

```bash
git clone <this-repo>
cd sri-code-maintenance-agent
uv sync
```

This installs the runtime dependency (`claude-agent-sdk`) and the `sri-agent` command into the
project environment.

## Authentication

The agent needs credentials for the Claude Agent SDK. Use **either**:

- **API key:** set an environment variable —
  ```bash
  export ANTHROPIC_API_KEY="sk-ant-..."
  ```
- **Existing Claude Code session:** if you've signed in with the `claude` CLI, the SDK reuses
  that session — no key needed.

If authentication is missing or invalid, the CLI prints a clear message instead of a stack trace.

## Usage

```bash
uv run sri-agent --repo /path/to/target-repo
```

You'll get an interactive prompt. Type a request; type `exit` or `quit` (or press Ctrl-D) to end
the session. Example:

```
you> Where is the function parse_config defined?
Agent: It's defined in src/app/config.py at line 42 ...

you> Add a docstring to it.
[permission] Edit wants to run: edit src/app/config.py
Allow? [y/N] y
Agent: Added a docstring describing the return value ... running tests ...
```

### Options

| Flag | Description |
|------|-------------|
| `--repo <path>` | **Required.** Path to the target repository. The agent works only inside this directory. |
| `--allow-writes` | Auto-accept file edits instead of prompting before each write. Off by default. |
| `--model <name>` | Override the model (e.g. a specific Claude model id). |
| `--max-turns <n>` | Cap agent turns per request (default: 20) to bound runaway loops. |
| `--test-timeout <s>` | Timeout for the `run_tests` tool (default: 120s). |
| `-v`, `--verbose` | Enable debug logging. |

You can also run it as a module: `uv run python -m sri_agent --repo <path>`.

## Safety model

- **Ask before writing.** By default every file write or shell command asks for confirmation.
  `--allow-writes` switches to auto-accepting edits. It never bypasses permissions entirely.
- **Never operates on itself.** The CLI refuses to run if `--repo` points at this agent's own
  source tree.
- **Dirty-tree warning.** At startup it warns if the target repo has uncommitted changes, so you
  can distinguish the agent's edits from your own.
- **Bounded test runs.** `run_tests` runs pytest in a subprocess with a timeout and never uses a
  shell on untrusted input.

## Observability

Tool invocations and end-of-turn token usage / cost are logged to stderr (agent output stays on
stdout). Use `--verbose` for more detail.

## Development

```bash
uv run pytest        # run the unit tests
uv run ruff check .  # lint
uv run ruff format . # format
```

Before shipping a change, also walk `evals/cases.md` manually against a throwaway repo — that's
the habit that keeps the agent trustworthy.

## Project layout

```
src/sri_agent/
  cli.py       # argument parsing + interactive loop
  agent.py     # SDK options, system prompt, permissions, streaming
  tools.py     # run_tests custom tool + in-process MCP server
  safety.py    # repo-path checks, same-dir refusal, git-dirty check
tests/         # unit tests for the parser and safety layer
evals/cases.md # manual evaluation cases
docs/          # project specification
```

## License

MIT — see [LICENSE](LICENSE).
