#!/usr/bin/env bash
# Developer bootstrap: create venv, install dev extras, run fast checks.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"

ruff check .
ruff format . --check
pytest -q tests/unit
