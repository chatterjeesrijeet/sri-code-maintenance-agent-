"""Enable ``python -m sri_agent`` as an alias for the ``sri-agent`` CLI."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
