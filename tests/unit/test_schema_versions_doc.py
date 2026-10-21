"""docs/reference/schema-versions.md lists every schema the package ships (#257)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "src" / "hpc_oda_commons" / "schemas" / "oda"
PAGE = ROOT / "docs" / "reference" / "schema-versions.md"


def _shipped() -> set[str]:
    return {f"oda.{p.parent.name}.{p.stem}" for p in SCHEMAS.glob("*/v*.json")}


def test_every_schema_file_is_on_the_page() -> None:
    page = PAGE.read_text(encoding="utf-8")
    missing = sorted(s for s in _shipped() if f"`{s}`" not in page)
    assert not missing, f"add these schemas to {PAGE.name}: {missing}"


def test_every_listed_schema_with_a_file_link_exists() -> None:
    page = PAGE.read_text(encoding="utf-8")
    linked = re.findall(
        r"\(\.\./\.\./src/hpc_oda_commons/schemas/oda/([a-z_]+)/(v[\d.]+)\.json\)", page
    )
    assert linked, "the page links no schema files"
    assert {f"oda.{kind}.{version}" for kind, version in linked} <= _shipped()
