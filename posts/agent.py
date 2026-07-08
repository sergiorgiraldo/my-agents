"""
linkedin_agent.py

Human-in-the-loop LinkedIn commenting agent for Sergio Giraldo
(https://www.linkedin.com/in/sergiorgiraldo/).

Each run it:
  1. Maintains a cached list of 10-15 industry leaders and 10 peers in
     Sergio's space (engineering leadership, AI/LLM ops, SRE, fintech,
     data architecture, data science, data integration, software architecture), stored in people.json next to this script.
     Re-researched only when the cache is missing or --refresh-people is passed or cache older than 5 days.
  2. Searches for recent, real LinkedIn posts from 2 leaders + 2 peers.
  3. Drafts a comment for each post that adds a distinct perspective
     (agrees-and-extends, respectfully pushes back, or brings a data
     point/experience the post doesn't cover) -- never a plain
     agreement ("Great post!", "So true!", etc are banned).

The agent never posts anything itself. It only prints link + draft
comment. You read, edit if you want, and post manually -- that's the
human-in-the-loop part.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."   # or be logged in via `claude login`
    pip install claude-agent-sdk python-dotenv
    python linkedin_agent.py                # normal run, reuse cached people list
    python linkedin_agent.py --refresh-people   # re-research leaders/peers first
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get(
    "CLAUDE_CODE_USE_LOGIN"
):
    import shutil
    import subprocess

    logged_in = False
    if shutil.which("claude"):
        try:
            result = subprocess.run(
                ["claude", "auth", "status"], capture_output=True, text=True, timeout=10
            )
            logged_in = '"loggedIn": true' in result.stdout
        except Exception:
            pass

    if not logged_in:
        print(
            "No ANTHROPIC_API_KEY and not logged in via `claude login`.\n"
            "Either add a .env file next to this script:\n"
            "  ANTHROPIC_API_KEY=sk-ant-...\n"
            "or run `claude login`.",
            file=sys.stderr,
        )
        sys.exit(1)

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    query,
)

PROFILE_URL = "https://www.linkedin.com/in/sergiorgiraldo/"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PEOPLE_FILE = os.path.join(SCRIPT_DIR, "people.json")


def build_prompt(refresh_people: bool) -> str:
    people_step = (
        f"""
STEP 1 -- Build the people list (people.json does not exist yet, or a refresh
was requested, so you must research it from scratch):

a. WebFetch {PROFILE_URL} to confirm Sergio's current headline, role, and
   the topics he posts about (engineering leadership, AI/LLM ops, SRE,
   fintech, data architecture -- confirm or correct this from the real page).
b. Use WebSearch (several distinct queries, e.g. "site:linkedin.com/in
   <topic> CTO", "<topic> engineering leader linkedin") to find:
     - 10 to 15 INDUSTRY LEADERS: recognized, senior voices (VP/CTO/staff+
       level or well-known independent voices) who post regularly in
       Sergio's space.
     - 10 PEERS: engineering-leader-level people, less famous than the
       leaders, who post good original content regularly (not just reposts).
c. Only include a person if you found a real linkedin.com/in/... URL for
   them in actual search results. Never invent a name or URL. If you can't
   find a confident URL for someone, drop them rather than guess.
d. Write the result to {PEOPLE_FILE} via the Write tool as JSON:
   {{"leaders": [{{"name": ..., "url": ..., "why": ...}}, ...],
     "peers": [{{"name": ..., "url": ..., "why": ...}}, ...]}}
"""
        if refresh_people
        else f"""
STEP 1 -- Load the existing people list:
a. Read {PEOPLE_FILE} (it already exists) to get the cached leaders and peers.
"""
    )

    return f"""
You are Sergio Giraldo's LinkedIn morning commenting assistant. His profile:
{PROFILE_URL}
He leads engineering teams at the intersection of data, AI, and financial
services (ING, Amsterdam). Goal: increase his visibility by leaving thoughtful
comments that ADD A PERSPECTIVE, not agreement.

{people_step}

STEP 2 -- Find 4 real, recent posts to comment on:
a. Pick 2 people from "leaders" and 2 from "peers" in the people list.
b. For each, use WebSearch (e.g. "site:linkedin.com/posts/<slug-or-name>",
   or "<name> linkedin post <recent topic>") to find an ACTUAL recent post
   URL of theirs (posted in roughly the last 1-2 weeks if you can tell).
   Only use a URL that appears in real search results -- never fabricate a
   linkedin.com/posts/... URL. If you cannot find a verifiable recent post
   for someone, pick a different person from the same list (leader/peer)
   rather than invent one. If after reasonable effort you still can't find
   4 verifiable posts, report fewer and say clearly which slots are missing
   and why -- do not fill the gap with a made-up link.
c. For each post found, briefly note what it's actually about (from the
   search result snippet or a WebFetch of the post URL if needed).

STEP 3 -- Draft one comment per post:
- The comment must add a distinct perspective: extend the idea with a
  concrete detail/experience, respectfully challenge an assumption, or
  connect it to a related tradeoff -- grounded in Sergio's background
  (engineering leadership, AI/LLM ops, SRE, fintech, data architecture).
- Never a bare agreement. Banned openers: "Great post", "So true", "Love this",
  "Couldn't agree more", "This!".
- Keep each comment 2-4 sentences, written in first person as Sergio,
  professional but conversational LinkedIn tone. No hashtags, no emoji spam
  (one emoji max, optional).

STEP 4 -- Output a final report into a file named <yyyy-mm-dd>.txt, plain text, in exactly this format for each
of the 4 posts (leaders first, then peers):

  [LEADER 1] <name>
  Link: <post url>
  Comment: <comment text>

  [LEADER 2] <name>
  Link: <post url>
  Comment: <comment text>

  [PEER 1] <name>
  Link: <post url>
  Comment: <comment text>

  [PEER 2] <name>
  Link: <post url>
  Comment: <comment text>

You are not posting anything -- Sergio reads this and posts manually.
"""


async def run_agent(refresh_people: bool):
    options = ClaudeAgentOptions(
        allowed_tools=["Read", "Write", "WebFetch", "WebSearch"],
        permission_mode="acceptEdits",
        cwd=SCRIPT_DIR,
    )

    prompt = build_prompt(refresh_people)

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
    refresh = "--refresh-people" in sys.argv or not os.path.isfile(PEOPLE_FILE)
    asyncio.run(run_agent(refresh))
