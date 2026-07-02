"""
folder_agent.py

A Claude agent that scans a folder for .txt files, treats each file's
contents as an instruction, executes the instruction, writes the result
to {original}.answer.txt, and renames the original to {original}.processed.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."   # or be logged in via `claude login`
    pip install claude-agent-sdk
    python folder_agent.py /Users/avenuecreek/tmp/playground/agent101
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY (and anything else) from a .env file next to this
# script, so the agent doesn't fall back to interactive `claude login`.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

if not os.environ.get("ANTHROPIC_API_KEY"):
    print(
        "ANTHROPIC_API_KEY not set. Add it to a .env file next to this script:\n"
        "  ANTHROPIC_API_KEY=sk-ant-...",
        file=sys.stderr,
    )
    sys.exit(1)

from claude_agent_sdk import (
    query,
    tool,
    create_sdk_mcp_server,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)


def make_rename_tool(root: str):
    """Builds a rename_file tool that can only touch files inside `root`."""

    @tool(
        "rename_file",
        "Rename a file. Only works on files inside the target folder.",
        {"old_name": str, "new_name": str},
    )
    async def rename_file(args):
        old_path = os.path.join(root, args["old_name"])
        new_path = os.path.join(root, args["new_name"])

        # Safety: refuse to escape the target folder
        if not os.path.abspath(old_path).startswith(os.path.abspath(root)):
            return {"content": [{"type": "text", "text": "Refused: path escapes target folder."}]}
        if not os.path.isfile(old_path):
            return {"content": [{"type": "text", "text": f"Error: {old_path} does not exist."}]}

        os.rename(old_path, new_path)
        return {"content": [{"type": "text", "text": f"Renamed {args['old_name']} -> {args['new_name']}"}]}

    return rename_file


async def run_agent(folder: str):
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        print(f"Folder does not exist: {folder}")
        sys.exit(1)

    rename_tool = make_rename_tool(folder)
    tool_server = create_sdk_mcp_server(
        name="fileops",
        version="1.0.0",
        tools=[rename_tool],
    )

    prompt = f"""
You are a file-processing agent. Your working folder is: {folder}

Do the following:
1. List the .txt files directly inside that folder (use Glob with pattern "*.txt").
   Skip any file that already ends in ".answer.txt" — those are outputs, not inputs.
2. For each remaining .txt file:
   a. Read its contents. The contents are an instruction written in plain
      language (e.g. a question to answer, a short task to perform).
   b. Carry out the instruction yourself and produce the result.
   c. Write the result to a new file in the same folder named
      "{{original_filename}}.answer.txt" (e.g. "task1.txt" -> "task1.txt.answer.txt").
      Use the Write tool for this.
   d. Rename the original file to "{{original_filename}}.processed" using the
      rename_file tool (e.g. "task1.txt" -> "task1.txt.processed").
3. When every file has been processed, print a short summary: for each file,
   the instruction you found and a one-line summary of the answer you wrote.

Process files one at a time and do not skip any step for any file.
"""

    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Glob", "mcp__fileops__rename_file"],
        mcp_servers={"fileops": tool_server},
        permission_mode="acceptEdits",  # auto-approve Read/Write/rename, no interactive prompts
        cwd=folder,
    )

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(block.text)
                elif isinstance(block, ToolUseBlock):
                    print(f"  [tool call] {block.name}({block.input})")
                elif isinstance(block, ToolResultBlock):
                    print(f"  [tool result] {block.content}")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    asyncio.run(run_agent(target))
