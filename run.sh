#!/usr/bin/env bash
# Everything, start to finish. Needs Python 3.11+ and Java 17.
#   ./run.sh          1,500 Illinois patients, seed 7
#   ./run.sh 150      a quick look
set -euo pipefail
cd "$(dirname "$0")"
SIZE="${1:-1500}"; SEED="${2:-7}"; LABEL="${3:-il-7}"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e ".[dev]"
fi
.venv/bin/python -m carelake all --size "$SIZE" --seed "$SEED" --label "$LABEL" --fresh
echo; echo "page:  .venv/bin/python -m http.server -d web 8080"
