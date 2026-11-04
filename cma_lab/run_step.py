"""Run one basket step with a hard timeout and process-group cleanup."""
from __future__ import annotations

import os
import signal
import subprocess
import sys


def run(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: run_step.py TIMEOUT_SECONDS COMMAND [ARGS...]", file=sys.stderr)
        return 2
    try:
        timeout_s = float(argv[0])
    except ValueError:
        print("timeout must be a number of seconds", file=sys.stderr)
        return 2
    if timeout_s <= 0:
        print("timeout must be positive", file=sys.stderr)
        return 2

    process = subprocess.Popen(argv[1:], start_new_session=True)
    try:
        return process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass
        print(f"step exceeded {timeout_s:g}s and was terminated", file=sys.stderr)
        return 124


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))