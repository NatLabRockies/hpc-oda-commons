from __future__ import annotations

import importlib.resources as ir
from pathlib import Path

from hpc_oda_commons.datasets.descriptor import load_descriptor
from hpc_oda_commons.registry.snapshot import load_registry_snapshot


def test_registered_datasets_have_valid_descriptors() -> None:
    """Every `dataset` registry entry must point at a bundled, valid descriptor whose
    id matches and whose targets include the registered output schema."""
    snapshot = load_registry_snapshot()
    datasets = [e for e in snapshot.entries if e.entry_type == "dataset"]
    assert datasets, "expected at least one registered dataset entry"

    base = ir.files("hpc_oda_commons")
    for entry in datasets:
        assert entry.reference is not None and entry.reference.kind == "path"
        rel = entry.reference.path or ""
        assert rel.startswith("hpc_oda_commons/"), rel
        resource = base / rel[len("hpc_oda_commons/") :]
        assert resource.is_file(), f"missing bundled descriptor: {rel}"

        descriptor = load_descriptor(Path(str(resource)))
        assert descriptor.dataset_id == entry.id
        if entry.output_schema_version:
            assert any(t.schema == entry.output_schema_version for t in descriptor.targets), (
                f"{entry.id}: no target produces {entry.output_schema_version}"
            )
