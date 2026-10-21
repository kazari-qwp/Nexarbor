# demo.py

import json
import os
import sys

# Locate the repository root (this file lives in <repo>/examples/demo.py) and
# make sure the in-repository ``hone`` package is importable, no matter from
# which working directory the demo is launched.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from hone.hone import Hone  # noqa: E402

TASK_DIR = os.environ.get("HONE_TASK_DIR")
if TASK_DIR:
    csv_filepath = os.path.join(TASK_DIR, "examples", "example_a.csv")
else:
    csv_filepath = os.path.join(REPO_ROOT, "examples", "example_a.csv")

# Create a Hone instance
hone_instance = Hone()

# Convert the CSV into a nested JSON structure
json_structure = hone_instance.convert(csv_filepath)

# Print the resulting JSON structure
print(json.dumps(json_structure, indent=2))
