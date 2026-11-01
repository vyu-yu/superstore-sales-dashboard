from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
APP_SCRIPT = PROJECT_ROOT / "dashboard" / "app.py"


def main() -> int:
    if not VENV_PYTHON.is_file():
        print(f"Project Python was not found: {VENV_PYTHON}")
        return 1

    if not APP_SCRIPT.is_file():
        print(f"Dashboard entry was not found: {APP_SCRIPT}")
        return 1

    command = [
        str(VENV_PYTHON),
        "-m",
        "streamlit",
        "run",
        str(APP_SCRIPT),
        "--browser.gatherUsageStats",
        "false",
    ]

    print("Starting Superstore Dashboard...")
    print("URL: http://localhost:8501")
    print("Close this window or press Ctrl+C to stop.")
    return subprocess.call(command, cwd=PROJECT_ROOT)


if __name__ == "__main__":
    sys.exit(main())
