from __future__ import annotations

import argparse
import os
import subprocess
import sys

from _bootstrap import PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the project test suite.")
    parser.add_argument("pytest_args", nargs="*", help="Additional pytest arguments.")
    args = parser.parse_args()

    temp_dir = PROJECT_ROOT / ".tmp"
    pytest_temp_dir = temp_dir / "pytest"
    cache_dir = temp_dir / "pytest-cache"
    pytest_temp_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    environment = os.environ.copy()
    environment.update(
        {
            "TMP": str(temp_dir),
            "TEMP": str(temp_dir),
            "TMPDIR": str(temp_dir),
        }
    )

    command = [
        sys.executable,
        "-m",
        "pytest",
        "--basetemp",
        str(pytest_temp_dir),
        "-o",
        f"cache_dir={cache_dir}",
        *args.pytest_args,
    ]
    return subprocess.run(command, cwd=PROJECT_ROOT, env=environment, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
