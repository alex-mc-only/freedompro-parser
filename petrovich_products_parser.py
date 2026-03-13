"""Backward-compatible entrypoint.

Use `python main.py bootstrap` and `python main.py collect` for the new workflow.
"""

from main import run


if __name__ == "__main__":
    raise SystemExit(run())
