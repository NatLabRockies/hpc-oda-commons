"""
Prepare orchestrator: fetch -> decode -> normalize -> validate -> manifest.

Produces, for each (selected) target of a descriptor, a canonical ODA table plus a
quality report and a manifest, at the target's declared output path (resolved under
``out_root``). The result is exactly the artifact a benchmark recipe consumes via
``dataset.table_path``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hpc_oda_commons.datasets.decode import decode_to_parquet
from hpc_oda_commons.datasets.descriptor import Descriptor
from hpc_oda_commons.datasets.fetch import DEFAULT_MAX_BYTES, fetch_descriptor
from hpc_oda_commons.datasets.normalize import normalize_target
from hpc_oda_commons.kernel.artifacts.manifest import new_manifest, write_manifest
from hpc_oda_commons.kernel.provenance import build_provenance
from hpc_oda_commons.schema.validator import validate_parquet_with_quality


@dataclass(frozen=True)
class PrepareResult:
    dataset_id: str
    target_schema: str
    output_id: str
    table_path: Path
    manifest_path: Path
    quality_path: Path
    summary: dict[str, Any]


def _resolve(out_root: Path, output_path: str) -> Path:
    candidate = Path(output_path)
    return candidate if candidate.is_absolute() else Path(out_root) / candidate


def prepare_descriptor(
    descriptor: Descriptor,
    *,
    cache_dir: Path,
    out_root: Path,
    slice_name: str | None = None,
    select_all: bool = False,
    target_schema: str | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
    allow_large: bool = False,
    offline: bool = False,
    assume_yes: bool = False,
    source_dir: Path | None = None,
    descriptor_sha256: str | None = None,
    batch_size: int = 50_000,
) -> list[PrepareResult]:
    """Fetch, decode, and normalize a descriptor into canonical ODA tables."""
    targets = [t for t in descriptor.targets if target_schema is None or t.schema == target_schema]
    if not targets:
        raise ValueError(f"no target matches schema {target_schema!r}")

    fetch_result = fetch_descriptor(
        descriptor,
        cache_dir=cache_dir,
        slice_name=slice_name,
        select_all=select_all,
        max_bytes=max_bytes,
        allow_large=allow_large,
        offline=offline,
        assume_yes=assume_yes,
        source_dir=source_dir,
        descriptor_sha256=descriptor_sha256,
    )
    raw_files = [r.path for r in fetch_result.resources]

    intermediate = Path(cache_dir) / descriptor.dataset_id / "intermediate.parquet"
    decode_to_parquet(
        str(descriptor.decode.get("format")),
        raw_files,
        intermediate,
        options=descriptor.decode.get("options") or {},
    )

    results: list[PrepareResult] = []
    for target in targets:
        table_path = _resolve(out_root, target.output_path)
        summary = normalize_target(intermediate, target, table_path, batch_size=batch_size)

        quality_path = table_path.with_suffix(".parquet.quality.json")
        validate_parquet_with_quality(
            table_path,
            schema_id=target.schema,
            sample=10,
            strict=False,
            report_path=quality_path,
        )

        manifest_path = table_path.parent / "manifest.json"
        provenance = build_provenance(
            input_schema=target.schema,
            result_schema="oda.result.v0.1.0",
            inputs=[table_path],
            project_root=out_root,
            capture_packages=False,
        )
        manifest = new_manifest(
            input_schema_version=target.schema,
            adapter=None,
            inputs=[{"path": r.filename, "sha256": r.sha256} for r in fetch_result.resources],
            artifact={
                "type": "dataset_prepare",
                "dataset_id": descriptor.dataset_id,
                "slice": fetch_result.slice,
                "paths": {
                    "table": str(table_path),
                    "manifest": str(manifest_path),
                    "lockfile": str(fetch_result.lockfile_path),
                },
            },
            provenance=provenance,
            transformations=[
                {"kind": "dataset_normalize", "output_schema": target.schema, "summary": summary}
            ],
        )
        write_manifest(manifest_path, manifest, validate=True)

        results.append(
            PrepareResult(
                dataset_id=descriptor.dataset_id,
                target_schema=target.schema,
                output_id=target.output_id,
                table_path=table_path,
                manifest_path=manifest_path,
                quality_path=quality_path,
                summary=summary,
            )
        )
    return results
