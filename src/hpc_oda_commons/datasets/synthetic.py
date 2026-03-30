"""
Synthetic dataset generation for HPC ODA Commons.
"""

from __future__ import annotations

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
        if value in (None, ""):
            continue
        text = str(value)
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        hour_bins.add(
            dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()
        )

    return len(hour_bins) >= 3


def generate_tiny_runtime_dataset(out_dir: Path) -> tuple[Path, Path]:
    """
    Deterministically generate a tiny synthetic dataset in Parquet + minimal manifest JSON.
    No network access required.
    """
    import json

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
                "submit_time": submit.isoformat().replace("+00:00", "Z"),
                "start_time": start.isoformat().replace("+00:00", "Z"),
                "end_time": end.isoformat().replace("+00:00", "Z"),
                "runtime_seconds": runtime,
                "allocated_cpus": int((i % 8) + 1),
                "partition": "debug" if i % 2 == 0 else "compute",
            }
        )

    write_table_parquet(rows, table_path)
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta = {
        "schema_version": "oda.job.v0.1.0",
        "generated_at": now_iso,
        "description": (
            "Deterministic tiny synthetic dataset for v0.1 job runtime prediction "
            "with submit_time for rolling-hour compatibility."
        ),
        "table_path": str(table_path),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return table_path, meta_path
