"""
folder_agent_loop.py

Cron-friendly version of folder_agent.py: runs ONE pass over the target
folder, processes any unprocessed .txt files, logs what it did, and exits.
Cron handles the repetition — this script does not loop internally.

Usage (manual test):
    python3 folder_agent_loop.py /Users/avenuecreek/tmp/playground/agent101

Crontab (every 5 minutes):
    */5 * * * * cd /Users/avenuecreek/source/my-agents && \
        /Users/avenuecreek/source/my-agents/venv/bin/python3 folder_agent_loop.py \
        /Users/avenuecreek/tmp/playground/agent101 >> /Users/avenuecreek/source/my-agents/agent.log 2>&1
"""

import asyncio
import fcntl
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Load ANTHROPIC_API_KEY (and anything else) from a .env file next to this
# script. Critical for cron: cron does not inherit your shell environment or
# any interactive `claude login` session, so without this the SDK has
# nothing to authenticate with.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from claude_agent_sdk import (
    query,
    tool,
    create_sdk_mcp_server,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ToolUseBlock,
)

LOCK_FILENAME = ".folder_agent.lock"
LOG_FILENAME = "folder_agent.log"


def setup_logging(folder: str) -> logging.Logger:
    log_path = os.path.join(folder, LOG_FILENAME)
    logger = logging.getLogger("folder_agent")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler(log_path)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    # Also echo to stdout so it shows up in cron's captured output / mail
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(stream)
    return logger


def acquire_lock(folder: str):
    """
    Returns an open file handle holding an exclusive lock, or None if another
    run is already in progress. Caller must keep the handle alive until done.
    """
    lock_path = os.path.join(folder, LOCK_FILENAME)
    fh = open(lock_path, "w")
    try:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def release_lock(fh):
    if fh:
        fcntl.flock(fh, fcntl.LOCK_UN)
        fh.close()


def make_rename_tool(root: str):
    @tool(
        "rename_file",
        "Rename a file. Only works on files inside the target folder.",
        {"old_name": str, "new_name": str},
    )
    async def rename_file(args):
        old_path = os.path.join(root, args["old_name"])
        new_path = os.path.join(root, args["new_name"])
        if not os.path.abspath(old_path).startswith(os.path.abspath(root)):
            return {"content": [{"type": "text", "text": "Refused: path escapes target folder."}]}
        if not os.path.isfile(old_path):
            return {"content": [{"type": "text", "text": f"Error: {old_path} does not exist."}]}
        os.rename(old_path, new_path)
        return {"content": [{"type": "text", "text": f"Renamed {args['old_name']} -> {args['new_name']}"}]}

    return rename_file


def has_pending_files(folder: str) -> bool:
    """Cheap pre-check so we don't spend an API call when there's nothing to do."""
    for name in os.listdir(folder):
        if name.endswith(".txt") and not name.endswith(".answer.txt"):
            return True
    return False


async def run_agent(folder: str, logger: logging.Logger) -> None:
    rename_tool = make_rename_tool(folder)
    tool_server = create_sdk_mcp_server(name="fileops", version="1.0.0", tools=[rename_tool])

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
      "{{original_filename}}.answer.txt". Use the Write tool.
   d. Rename the original file to "{{original_filename}}.processed" using the
      rename_file tool.
3. If there are no matching .txt files, say so and stop — do not invent files.
4. When done, print a one-line summary per file processed.

Process files one at a time and do not skip any step for any file.
"""

    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "Glob", "mcp__fileops__rename_file"],
        mcp_servers={"fileops": tool_server},
        permission_mode="acceptEdits",
        cwd=folder,
    )

    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    logger.info(block.text.strip())
                elif isinstance(block, ToolUseBlock):
                    logger.info(f"[tool call] {block.name}({block.input})")


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "."
    folder = os.path.abspath(folder)

    if not os.path.isdir(folder):
        print(f"Folder does not exist: {folder}", file=sys.stderr)
        sys.exit(1)

    logger = setup_logging(folder)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error(
            "ANTHROPIC_API_KEY not set. Add it to a .env file next to this script: "
            "ANTHROPIC_API_KEY=sk-ant-..."
        )
        sys.exit(1)

    lock_fh = acquire_lock(folder)
    if lock_fh is None:
        logger.info("Another run is already in progress — skipping this pass.")
        sys.exit(0)

    try:
        logger.info(f"--- Run started {datetime.now().isoformat()} ---")

        if not has_pending_files(folder):
            logger.info("No unprocessed .txt files found. Nothing to do.")
            return

        try:
            asyncio.run(run_agent(folder, logger))
        except Exception as e:
            logger.error(f"Agent run failed: {e}")
            sys.exit(1)

        logger.info("--- Run finished ---")
    finally:
        release_lock(lock_fh)


if __name__ == "__main__":
    main()
