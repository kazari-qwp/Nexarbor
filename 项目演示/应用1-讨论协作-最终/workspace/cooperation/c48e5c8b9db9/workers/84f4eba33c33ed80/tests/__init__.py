"""Shared test helpers for the hone test suite.

Follows the FINAL plan (CONTRACT.md): fixture copies are committed in the
repository; ``HONE_TASK_DIR`` may point at the original read-only task folder.
Never silently skip: a missing task folder raises FileNotFoundError.
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Absolute path of the repository root (parent of this ``tests`` package)."""
    return Path(__file__).resolve().parent.parent


def fixtures_dir() -> Path:
    """Absolute path of the committed, byte-identical fixture tree."""
    return Path(__file__).resolve().parent / "fixtures"


def _candidate_task_dirs() -> list[Path]:
    root = repo_root()
    candidates: list[Path] = []
    env = os.environ.get("HONE_TASK_DIR")
    if env:
        candidates.append(Path(env))
    candidates.extend(
        [
            root / "workspace" / "task",
            root.parent / "workspace" / "task",
            root.parent.parent / "workspace" / "task",
            Path.cwd() / "workspace" / "task",
        ]
    )
    return candidates


def task_root() -> Path:
    """Locate the original task material directory.

    Resolution order: ``HONE_TASK_DIR`` -> ``repo_root/workspace/task`` ->
    ``repo_root/../../workspace/task`` -> ``cwd/workspace/task``.
    Raises FileNotFoundError instead of silently skipping.
    """
    for candidate in _candidate_task_dirs():
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (resolved / "INPUTS.md").is_file():
            return resolved
    tried = ", ".join(str(p) for p in _candidate_task_dirs())
    raise FileNotFoundError(
        "task_root(): cannot locate the hone task material (INPUTS.md); tried: " + tried
    )
