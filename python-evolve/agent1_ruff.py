"""
agent1_ruff.py

Triggered after a commit: runs ruff on the target folder, auto-fixes issues,
manually fixes anything ruff cannot, then commits with a conventional "chore" message.
Exits 0 on success (clean or fixed), non-zero on unrecoverable error.

Usage:
    python3 agent1_ruff.py /path/to/python-project
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

AGENT_NAME = "agent1_ruff"


async def run_agent(folder: str) -> None:
    prompt = f"""
You are a Python linting agent. Target folder: {folder}

Steps:
1. Run: ruff check {folder} --output-format=concise
   - If exit code 0 (no issues), print "ruff: clean — nothing to commit" and stop.
2. Run: ruff check {folder} --fix
3. Run ruff check again to see remaining issues.
4. For any remaining issues ruff could not auto-fix, read the offending file and
   fix the issue manually with Edit.
5. Run ruff one final time to confirm exit code 0.
6. Stage changes: git -C {folder} add -u
7. Commit: git -C {folder} commit -m "chore: fix ruff linting issues"
8. Print a one-line summary of files changed.

Never modify files outside {folder}.
If ruff is not installed, run: pip install ruff
"""

    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Edit"],
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
        print("agent1: no new commits since last run, skipping.")
        return
    asyncio.run(run_agent(folder))
    write_marker(folder, AGENT_NAME, get_head(folder))


if __name__ == "__main__":
    main()
