from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.adapters.base import AdapterMetadata, SourceAdapter
from hpc_oda_commons.adapters.slurmctld.adapter import SlurmctldAdapter


def test_slurmctld_adapter_metadata() -> None:
    adapter = SlurmctldAdapter()
    assert isinstance(adapter, SourceAdapter)
    assert isinstance(adapter.metadata, AdapterMetadata)
    assert adapter.metadata.id == "adapter.slurmctld"
    assert adapter.metadata.output_schema_version == "oda.job.v0.1.0"
    assert "slurmctld" in adapter.metadata.supported_sources


def test_slurmctld_adapter_parses_fixture(tmp_path: Path) -> None:
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
    adapter = SlurmctldAdapter()
    rows = adapter.parse(fixture)
    assert rows
