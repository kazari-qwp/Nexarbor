"""Application-wide model execution limits."""
import json
from pathlib import Path


def agent_defaults():
    return json.loads((Path(__file__).resolve().parents[2] / "configs/agent-defaults.json").read_text(encoding="utf-8"))
