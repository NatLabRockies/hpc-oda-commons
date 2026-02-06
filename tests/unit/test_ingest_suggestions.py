from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.qst.ingest_suggestions import build_ingest_suggestions
from tests.conftest import write_slurmctld_log


def test_build_ingest_suggestions_for_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "slurmctld.log"
    write_slurmctld_log(fixture)
    suggestions = build_ingest_suggestions(fixture)
    assert isinstance(suggestions, list)
