#! /bin/bash

# Run the demo from the repository root.
# Usage: bash examples/demo.sh
set -e
cd "$(dirname "$0")/.."
python examples/demo.py
