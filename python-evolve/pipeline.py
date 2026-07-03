"""
pipeline.py

Runs Agent 1 → Agent 2 → Agent 3 in sequence against a Python project folder.
Each agent runs as a subprocess so failures are isolated and the pipeline stops
on the first non-zero exit code.

Usage:
    python3 pipeline.py /path/to/python-project
"""

import subprocess
import sys
import os

AGENTS = [
    ("agent1_ruff.py",   "1/3 ruff lint + fix"),
    ("agent2_tests.py",  "2/3 write unit tests"),
    ("agent3_release.py","3/3 readme + release"),
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    folder = os.path.abspath(folder)

    if not os.path.isdir(folder):
        print(f"Not a directory: {folder}", file=sys.stderr)
        sys.exit(1)

    try:
        while True:
            for script, label in AGENTS:
                print(f"\n=== {label} ===")
                result = subprocess.run(
                    [sys.executable, os.path.join(SCRIPT_DIR, script), folder],
                    check=False,
                )
                if result.returncode != 0:
                    print(f"Pipeline stopped: {script} exited {result.returncode}", file=sys.stderr)
                    sys.exit(result.returncode)

            print("\nPipeline cycle complete. Restarting...")
    except KeyboardInterrupt:
        print("\nPipeline stopped by user.")


if __name__ == "__main__":
    main()
