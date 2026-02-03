"""
Entrypoint for `python -m hpc_oda_commons` (delegates to CLI).
"""
from __future__ import annotations

from hpc_oda_commons.qst.cli import app

if __name__ == "__main__":
    app()