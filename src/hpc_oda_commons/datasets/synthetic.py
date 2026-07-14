"""
Synthetic dataset generation for HPC ODA Commons.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.artifacts.oda_table import write_table_parquet


def tiny_dataset_is_rolling_compatible(table_path: Path) -> bool:
    """Check whether the tiny synthetic dataset has enough hourly spread for rolling splits."""
    try:
        import pyarrow.parquet as pq
    except Exception:
        return False

    try:
        table = pq.read_table(table_path)
    except Exception:
        return False

    if "submit_time" not in table.column_names:
        return False

    submit_values = table.column("submit_time").to_pylist()
    hour_bins: set[str] = set()
    for value in submit_values:
        if not isinstance(value, datetime):
            continue
        dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        hour_bins.add(
            dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
        )

    return len(hour_bins) >= 3


def generate_tiny_runtime_dataset(out_dir: Path) -> tuple[Path, Path]:
    """
    Deterministically generate a tiny synthetic dataset in Parquet + minimal manifest JSON.
    No network access required.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "data.parquet"
    meta_path = out_dir / "manifest.json"

    if (
        table_path.exists()
        and meta_path.exists()
        and tiny_dataset_is_rolling_compatible(table_path)
    ):
        return table_path, meta_path

    base_submit = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for i in range(30):
        submit = base_submit + timedelta(hours=i, minutes=2)
        start = submit + timedelta(minutes=3)
        runtime = float(600 + (i % 10) * 120)  # 600..1680 seconds
        end = start + timedelta(seconds=runtime)
        rows.append(
            {
                "job_id": 1001 + i,
                "submit_time": submit,
                "start_time": start,
                "end_time": end,
                "runtime_seconds": runtime,
                "allocated_cpus": int((i % 8) + 1),
                "partition": "debug" if i % 2 == 0 else "compute",
            }
        )

    write_table_parquet(rows, table_path)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = {
        "schema_version": "oda.job.v0.2.0",
        "generated_at": now_iso,
        "description": (
            "Deterministic tiny synthetic dataset for v0.1 job runtime prediction "
            "with submit_time for rolling-hour compatibility."
        ),
        "table_path": str(table_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return table_path, meta_path


def generate_tiny_embedded_runtime_dataset(out_dir: Path, *, dim: int = 16) -> tuple[Path, Path]:
    """Deterministically generate a tiny job table carrying a precomputed ``embedding`` column.

    Jobs belong to one of a few latent clusters; each cluster has a distinct base
    embedding and a distinct base runtime, so a nearest-neighbor in embedding space
    predicts runtime well. The embedding is written as a native Arrow
    ``FixedSizeList<float32>[dim]`` column (the format the embedding kNN model expects).
    No network access required.
    """
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_dir.mkdir(parents=True, exist_ok=True)
    table_path = out_dir / "data.parquet"
    meta_path = out_dir / "manifest.json"

    rng = np.random.default_rng(1234)
    n_clusters = 3
    cluster_base = rng.standard_normal((n_clusters, dim)).astype(np.float32)
    cluster_runtime = [600.0, 1200.0, 1800.0]

    base_submit = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for i in range(48):
        cluster = i % n_clusters
        submit = base_submit + timedelta(hours=i, minutes=2)
        start = submit + timedelta(minutes=3)
        runtime = cluster_runtime[cluster] + float((i % 5) * 10)
        end = start + timedelta(seconds=runtime)
        vec = cluster_base[cluster] + 0.02 * rng.standard_normal(dim).astype(np.float32)
        rows.append(
            {
                "job_id": 2001 + i,
                "submit_time": submit,
                "start_time": start,
                "end_time": end,
                "runtime_seconds": runtime,
                "allocated_cpus": int((i % 8) + 1),
                "partition": "debug" if cluster == 0 else "compute",
                "embedding": [float(x) for x in vec],
            }
        )

    schema = pa.schema(
        [
            pa.field("job_id", pa.int64()),
            pa.field("submit_time", pa.timestamp("us", tz="UTC")),
            pa.field("start_time", pa.timestamp("us", tz="UTC")),
            pa.field("end_time", pa.timestamp("us", tz="UTC")),
            pa.field("runtime_seconds", pa.float64()),
            pa.field("allocated_cpus", pa.int64()),
            pa.field("partition", pa.string()),
            pa.field("embedding", pa.list_(pa.float32(), dim)),
        ]
    )
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, table_path)

    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = {
        "schema_version": "oda.job.v0.2.0",
        "generated_at": now_iso,
        "description": (
            "Deterministic tiny synthetic dataset with a precomputed FixedSizeList "
            "embedding column for the embedding kNN runtime model."
        ),
        "table_path": str(table_path),
        "embedding": {"field": "embedding", "dim": dim, "normalized": False},
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return table_path, meta_path
