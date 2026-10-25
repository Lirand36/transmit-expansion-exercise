#!/bin/bash
# Double-click to run: sets up Python the first time, rebuilds the plan, and opens the submission page.
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt
python run.py
open submission/index.html
