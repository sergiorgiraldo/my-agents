"""
agent2_tests.py

Triggered after Agent 1 (ruff clean): discovers Python modules in the target
folder, writes pytest unit tests, runs them, and commits with a "chore" message.

Usage:
    python3 agent2_tests.py /path/to/python-project
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

if not os.environ.get("ANTHROPIC_API_KEY"):
    print("ANTHROPIC_API_KEY not set.", file=sys.stderr)
    sys.exit(1)

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    ToolUseBlock,
    query,
)

from pipeline_state import get_head, has_new_commit, write_marker

AGENT_NAME = "agent2_tests"


async def run_agent(folder: str) -> None:
    prompt = f"""
You are a test-writing agent. Target folder: {folder}

Steps:
1. List all .py files in {folder} (use Glob pattern "**/*.py").
   Exclude any files already named test_*.py or *_test.py.
2. Read each source file to understand what it does.
3. For each source file that has testable logic (functions, classes):
   a. Create (or update) a corresponding test file:
      - If source is {folder}/foo.py → write tests to {folder}/tests/test_foo.py
      - Use pytest style (plain functions, assert statements, no unittest classes).
      - Cover happy paths and key edge cases.
   b. Write the test file using the Write tool.
4. Run tests: pytest {folder} -v --tb=short
   - If any test fails, read the error, fix the test (or the logic if it is clearly
     wrong), and re-run until all tests pass.
5. Stage new/modified test files: git -C {folder} add -A
6. Commit: git -C {folder} commit -m "chore: add unit tests"
7. Print a one-line summary: number of test files created and tests written.

Never modify non-test source files.
If pytest is not installed, run: pip install pytest
"""

    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Write", "Glob"],
        permission_mode="acceptEdits",
        cwd=folder,
    )

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock) and block.text.strip():
                    print(block.text.strip())
                elif isinstance(block, ToolUseBlock):
                    print(f"[tool] {block.name}({block.input})")


def main() -> None:
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        print(f"Not a directory: {folder}", file=sys.stderr)
        sys.exit(1)
    if not has_new_commit(folder, AGENT_NAME):
        print("agent2: no new commits since last run, skipping.")
        return
    asyncio.run(run_agent(folder))
    write_marker(folder, AGENT_NAME, get_head(folder))


if __name__ == "__main__":
    main()
