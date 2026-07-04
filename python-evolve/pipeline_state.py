"""
pipeline_state.py

Tracks, per agent, the last git commit SHA it has processed for a given
target folder. Lets each pipeline stage skip its work when there has been
no new commit since it last ran, instead of relying on the LLM prompt to
"notice" nothing changed.

State is stored under <folder>/.git/pipeline_state/<agent>.sha so it never
gets staged or committed by the agents themselves.
"""

import os
import subprocess


def _state_dir(folder: str) -> str:
    path = os.path.join(folder, ".git", "pipeline_state")
    os.makedirs(path, exist_ok=True)
    return path


def _marker_path(folder: str, agent: str) -> str:
    return os.path.join(_state_dir(folder), f"{agent}.sha")


def get_head(folder: str) -> str:
    result = subprocess.run(
        ["git", "-C", folder, "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def read_marker(folder: str, agent: str) -> str | None:
    path = _marker_path(folder, agent)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read().strip() or None


def write_marker(folder: str, agent: str, sha: str) -> None:
    with open(_marker_path(folder, agent), "w", encoding="utf-8") as f:
        f.write(sha)


def has_new_commit(folder: str, agent: str) -> bool:
    """True if HEAD has moved since this agent last recorded a marker."""
    return read_marker(folder, agent) != get_head(folder)
