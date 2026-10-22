from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.adapters.base import AdapterMetadata, SourceAdapter
from hpc_oda_commons.adapters.slurmctld.adapter import SlurmctldAdapter
from tests.conftest import write_slurmctld_log


def test_slurmctld_adapter_metadata() -> None:
    adapter = SlurmctldAdapter()
    assert isinstance(adapter, SourceAdapter)
    assert isinstance(adapter.metadata, AdapterMetadata)
    assert adapter.metadata.id == "adapter.slurmctld"
    assert adapter.metadata.output_schema_version == "oda.job.v0.2.0"
    assert "slurmctld" in adapter.metadata.supported_sources


def test_slurmctld_adapter_parses_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "slurmctld.log"
    write_slurmctld_log(fixture)
    adapter = SlurmctldAdapter()
    rows = adapter.parse(fixture)
    assert rows


def test_adapter_metadata_is_its_registry_entry() -> None:
    """The adapter reads its name and version from adapter.yml, as the registry does (#259)."""
    from hpc_oda_commons.adapters.slurmctld.adapter import SLURMCTLD_METADATA
    from hpc_oda_commons.registry.snapshot import load_registry_snapshot

    entry = next(e for e in load_registry_snapshot(None).entries if e.id == SLURMCTLD_METADATA.id)
    assert (entry.name, entry.version) == (SLURMCTLD_METADATA.name, SLURMCTLD_METADATA.version)
