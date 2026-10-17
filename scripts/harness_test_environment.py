"""Keep native test subprocess temporary files alongside ignored build outputs."""
import os
from pathlib import Path


def harness_test_environment(**overrides):
    root=Path(__file__).resolve().parents[1]/'build'/'harness-temp'
    root.mkdir(parents=True,exist_ok=True)
    return {**os.environ,**overrides,'TEMP':str(root),'TMP':str(root),'TMPDIR':str(root)}
