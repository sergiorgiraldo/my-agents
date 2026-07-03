"""
agent3_release.py

Triggered after Agent 2 (tests green): updates the README, commits with a
conventional "feat" message, pushes, and tags a new minor semver release.

Semver logic: reads the latest git tag (vMAJOR.MINOR.PATCH), bumps MINOR,
resets PATCH to 0. If no tag exists, starts at v0.1.0.

Usage:
    python3 agent3_release.py /path/to/python-project
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


async def run_agent(folder: str) -> None:
    prompt = f"""
You are a release agent. Target folder: {folder}

Steps:
1. Determine the next minor version:
   a. Run: git -C {folder} describe --tags --abbrev=0 2>/dev/null || echo "none"
   b. If output is "none", next version is v0.1.0.
   c. Otherwise parse vMAJOR.MINOR.PATCH → bump MINOR by 1, set PATCH to 0.
      Example: v1.3.2 → v1.4.0

2. Update the README:
   a. Read the existing README (README.md or README.rst) in {folder}.
      If none exists, create README.md.
   b. Add or update a section called "## Changelog" that lists:
      - The new version and today's date.
      - A short bullet list of what changed: linting fixes, new tests added,
        and any notable logic.
   c. Write the updated README with the Write tool.

3. Stage and commit:
   git -C {folder} add README.md
   git -C {folder} commit -m "feat: update readme for <new-version>"

4. Tag the new version:
   git -C {folder} tag <new-version>

5. Push branch and tags:
   git -C {folder} push
   git -C {folder} push --tags

6. Print: "Released <new-version>"

in conflict, always bump version

Do not modify any source or test files.
"""

    options = ClaudeAgentOptions(
        allowed_tools=["Bash", "Read", "Write"],
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
    asyncio.run(run_agent(folder))


if __name__ == "__main__":
    main()
