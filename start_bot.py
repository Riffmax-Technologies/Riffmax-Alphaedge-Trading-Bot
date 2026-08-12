#!/usr/bin/env python3
"""Start the AlphaEdge bot engine from one command.

This launches the autonomous scanner and Telegram control bot together,
then keeps both processes running until you stop the parent launcher.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable


def launch(script_name: str) -> subprocess.Popen:
    script_path = PROJECT_ROOT / script_name
    return subprocess.Popen(
        [PYTHON_EXE, str(script_path)],
        cwd=str(PROJECT_ROOT),
        stdout=None,
        stderr=None,
    )


def main() -> int:
    scanner = launch("run_autonomous_scanner.py")
    telegram = launch("telegram_bot.py")

    processes = [scanner, telegram]
    print("AlphaEdge engine started.")
    print(" - Autonomous scanner: running")
    print(" - Telegram bot: running")
    print("Press Ctrl+C to stop both processes.")

    try:
        while True:
            exit_codes = [proc.poll() for proc in processes]
            if any(code is not None for code in exit_codes):
                for proc in processes:
                    if proc.poll() is None:
                        proc.terminate()
                return next(code for code in exit_codes if code is not None) or 0
    except KeyboardInterrupt:
        print("\nStopping AlphaEdge engine...")
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
