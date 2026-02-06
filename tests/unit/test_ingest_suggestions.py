from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.qst.ingest_suggestions import build_ingest_suggestions


def test_build_ingest_suggestions_for_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "slurmctld.log"
    fixture.write_text(
        "\n".join(
            [
                "[2026-01-01T00:00:00.000] Allocate JobId=1 NodeList=node1 #CPUs=2 Partition=debug",
                "[2026-01-01T00:01:00.000] _job_complete: JobId=1 done",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    suggestions = build_ingest_suggestions(fixture)
    assert isinstance(suggestions, list)
