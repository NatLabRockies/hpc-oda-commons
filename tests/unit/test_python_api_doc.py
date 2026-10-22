"""docs/reference/python-api.md lists every function the intelligence package exports (#259)."""

from __future__ import annotations

from pathlib import Path

import hpc_oda_commons.intelligence as intelligence

PAGE = Path(__file__).resolve().parents[2] / "docs" / "reference" / "python-api.md"


def test_every_exported_function_is_documented() -> None:
    page = PAGE.read_text(encoding="utf-8")
    missing = [name for name in intelligence.__all__ if f"`{name}(" not in page]
    assert not missing, f"document these in {PAGE.name}: {missing}"
