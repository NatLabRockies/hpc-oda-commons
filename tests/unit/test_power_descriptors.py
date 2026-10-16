"""The job-power dataset descriptors: they must not collide with the runtime ones, and the
F-DATA UoPC window must deliver what the UoPC paper protocol reads (#125)."""

from __future__ import annotations

import importlib.resources as ir
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.datasets.descriptor import load_descriptor
from hpc_oda_commons.datasets.normalize import normalize_target
from hpc_oda_commons.models.job_power_uopc.model import JobPowerUopcModel
from hpc_oda_commons.schema.validator import validate_parquet_with_quality

_DESCRIPTORS = Path(str(ir.files("hpc_oda_commons") / "datasets" / "descriptors"))
_UOPC = _DESCRIPTORS / "job-power" / "fdata_fugaku_uopc.yml"


def test_every_prepared_table_has_its_own_path() -> None:
    """`datasets prepare` writes each target to its declared path, whatever slice was
    fetched. Two descriptors (or targets) sharing a path overwrite each other's table: the
    Fugaku runtime benchmark and the UoPC window would silently swap data."""
    owners: dict[str, str] = {}
    for path in sorted(_DESCRIPTORS.rglob("*.yml")):
        for target in load_descriptor(path).targets:
            assert target.output_path not in owners, (
                f"{path.name} and {owners[target.output_path]} both write {target.output_path}"
            )
            owners[target.output_path] = path.name


def test_fugaku_runtime_window_is_untouched_by_the_power_work() -> None:
    """The runtime benchmark keeps its seven-month curation (#154) and no slices: the UoPC
    months live in their own descriptor rather than as a slice that would change the
    runtime default."""
    runtime = load_descriptor(_DESCRIPTORS / "job-runtime" / "fdata_fugaku.yml")
    files = [r["filename"] for r in runtime.source["resources"]]
    assert files == [f"23_{m:02d}.parquet" for m in range(3, 10)]
    assert not runtime.source.get("slices")


def _fdata_month(path: Path) -> None:
    """A few rows shaped like an F-DATA monthly file (the columns this descriptor maps)."""
    n = 6
    stamp = [f"2024-02-0{i + 1}T10:00:00+09:00" for i in range(n)]
    finish = [f"2024-02-0{i + 1}T12:00:00+09:00" for i in range(n)]
    pq.write_table(
        pa.table(
            {
                "jid": [f"j{i}" for i in range(n)],
                "usr": ["alice"] * n,
                "jnam": ["run"] * n,
                "cnumr": pa.array([48] * n, pa.int64()),
                "cnumat": pa.array([48] * n, pa.int64()),
                "nnumr": pa.array([2] * n, pa.int64()),
                "nnuma": pa.array([2] * n, pa.int64()),
                "adt": stamp,
                "sdt": stamp,
                "edt": finish,
                "elpl": [7200.0] * n,
                "duration": [7200.0] * n,
                "ec": pa.array([0] * n, pa.int64()),
                "exit state": ["completed"] * n,
                "pclass": ["compute"] * n,
                "freq_req": pa.array([2200] * n, pa.int64()),
                "avgpcon": [200.0, 210.0, None, 230.0, 240.0, 250.0],
                "maxpcon": [300.0, 310.0, 320.0, 330.0, 340.0, 350.0],
                "embedding": pa.array(
                    [[0.1 * i, 0.2, 0.3] for i in range(n)], pa.list_(pa.float32())
                ),
            }
        ),
        path,
    )


def test_uopc_window_prepares_the_columns_the_paper_protocol_reads(tmp_path: Path) -> None:
    descriptor = load_descriptor(_UOPC)
    (target,) = descriptor.targets
    raw = tmp_path / "24_02.parquet"
    _fdata_month(raw)
    out = tmp_path / "data.parquet"

    summary = normalize_target(raw, target, out)

    table = pq.read_table(out)
    # The row with no avgpcon is dropped by the descriptor's filter.
    assert summary["rows_final"] == 5
    assert {
        "user",
        "submit_time",
        "end_time",
        "num_cores_req",
        "num_nodes_req",
        "num_nodes_alloc",
        "freq_req",
        "avgpcon",
        "maxpcon",
        "embedding",
    } <= set(table.column_names)
    assert pa.types.is_list(table.schema.field("embedding").type)
    validate_parquet_with_quality(out, schema_id="oda.job.v0.2.0", strict=True)

    # And the model accepts the prepared rows as they come off disk.
    model = JobPowerUopcModel()
    prepared = model._prepare_paper_data(table.to_pylist(), test_start="2024-02-01")
    assert len(prepared.avg_target_arr) == 5
    assert prepared.avg_target_arr[0] == 100.0  # 200 W over 2 allocated nodes
