"""The job-power dataset descriptors: they must not collide with the runtime ones, and the
F-DATA UoPC window must deliver what the UoPC paper protocol reads (#125)."""

from __future__ import annotations

import importlib.resources as ir
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.benchmarking.hpc.slice import read_window, slice_dataset
from hpc_oda_commons.datasets.descriptor import load_descriptor
from hpc_oda_commons.datasets.normalize import normalize_target
from hpc_oda_commons.models.uopc.model import UopcModel
from hpc_oda_commons.schema.validator import validate_parquet_with_quality

_DESCRIPTORS = Path(str(ir.files("hpc_oda_commons") / "datasets" / "descriptors"))
_FDATA = _DESCRIPTORS / "fdata_fugaku.yml"


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


def test_fdata_is_one_dataset_of_the_months_its_benchmarks_read() -> None:
    """F-DATA is one dataset (#249): the runtime benchmark's March-September 2023 and the
    power benchmark's December 2023-April 2024. Leaving out October and November keeps the
    power window's rows exactly those of the old UoPC table: a file holds a Japan-time
    month's submissions, so the window's first UTC day would catch November's last hours."""
    fdata = load_descriptor(_FDATA)
    files = [r["filename"] for r in fdata.source["resources"]]
    assert files == [f"23_{m:02d}.parquet" for m in range(3, 10)] + [
        "23_12.parquet",
        *(f"24_{m:02d}.parquet" for m in range(1, 5)),
    ]
    assert not fdata.source.get("slices")


def _fdata_month(path: Path, nnuma: list[int] | None = None) -> None:
    """A few rows shaped like an F-DATA monthly file (the columns this descriptor maps).
    Every job requests 2 nodes; ``nnuma`` overrides the allocated count."""
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
                "nnuma": pa.array(nnuma or [2] * n, pa.int64()),
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
    descriptor = load_descriptor(_FDATA)
    (target,) = descriptor.targets
    raw = tmp_path / "24_02.parquet"
    _fdata_month(raw)
    out = tmp_path / "data.parquet"

    summary = normalize_target(raw, target, out)

    # The descriptor keeps every row with a runtime; the power recipes then read only the
    # rows with both targets and an embedding, so the row with no avgpcon is left out.
    assert summary["rows_final"] == 6
    table = read_window(out, require_nonnull=["avgpcon_per_node", "maxpcon_per_node", "embedding"])
    assert table.num_rows == 5
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
    model = UopcModel()
    prepared = model._prepare_paper_data(table.to_pylist(), test_start="2024-02-01")
    assert len(prepared.avg_target_arr) == 5
    assert prepared.avg_target_arr[0] == 100.0  # 200 W over 2 allocated nodes


def test_uopc_window_derives_per_node_power(tmp_path: Path) -> None:
    """The targets every model predicts are computed once, during preparation (#204)."""
    (target,) = load_descriptor(_FDATA).targets
    raw = tmp_path / "24_02.parquet"
    _fdata_month(raw)
    out = tmp_path / "data.parquet"
    normalize_target(raw, target, out)

    rows = read_window(out, require_nonnull=["avgpcon_per_node"]).to_pylist()
    assert [r["avgpcon_per_node"] for r in rows] == [r["avgpcon"] / 2 for r in rows]
    assert [r["maxpcon_per_node"] for r in rows] == [r["maxpcon"] / 2 for r in rows]
    assert {"avgpcon_per_node", "maxpcon_per_node"} <= set(target.target_columns)


def test_per_node_power_divides_by_requested_nodes_not_a_padded_allocation(
    tmp_path: Path,
) -> None:
    """Fugaku can record more allocated nodes (nnuma) than a job runs on: 1-node, 48-core
    jobs show nnuma = 48 while their power is one node's. The prepared per-node targets
    divide by requested nodes, and so does the paper protocol by default (#228); its
    node_count="allocated" option divides by nnuma, as the paper does (#204)."""
    (target,) = load_descriptor(_FDATA).targets
    raw = tmp_path / "24_02.parquet"
    _fdata_month(raw, nnuma=[48, 2, 2, 2, 2, 2])
    out = tmp_path / "data.parquet"
    normalize_target(raw, target, out)

    rows = read_window(out, require_nonnull=["avgpcon_per_node"]).to_pylist()
    assert rows[0]["avgpcon_per_node"] == 100.0  # 200 W over 2 requested nodes, not 48
    assert rows[0]["maxpcon_per_node"] == 150.0

    model = UopcModel()
    prepared = model._prepare_paper_data(rows, test_start="2024-02-01")
    assert prepared.avg_target_arr[0] == 100.0
    paper = model._prepare_paper_data(rows, test_start="2024-02-01", node_count="allocated")
    assert paper.avg_target_arr[0] == 200.0 / 48


def test_fugaku_runtime_window_carries_power_without_changing_its_rows(tmp_path: Path) -> None:
    """Per-node power rides along on the runtime window, but its filter is still runtime:
    a job with no power reading keeps its runtime row (#204)."""
    (target,) = load_descriptor(_DESCRIPTORS / "fdata_fugaku.yml").targets
    assert target.filter == {"require_nonnull": ["runtime_seconds"]}

    raw = tmp_path / "23_07.parquet"
    _fdata_month(raw)
    out = tmp_path / "data.parquet"
    summary = normalize_target(raw, target, out)

    rows = pq.read_table(out).to_pylist()
    assert summary["rows_final"] == 6  # the row without avgpcon is kept
    assert [r["avgpcon_per_node"] for r in rows] == [100.0, 105.0, None, 115.0, 120.0, 125.0]
    # F-DATA's own embedding rides along; the runtime fleet's slice leaves it out, because
    # the runtime protocol embeds every dataset with `hpc-oda embed` (#249).
    assert "embedding" in rows[0]
    sliced = tmp_path / "window.parquet"
    slice_dataset(out, sliced, "2023-01-01", "2024-12-31", drop_columns=("embedding",))
    assert "embedding" not in pq.read_table(sliced).column_names


def test_pm100_power_is_its_node_trace_per_allocated_node(tmp_path: Path) -> None:
    """PM100's node_power_consumption is the job's total across its nodes (it scales with
    node count), so per-node power is the trace's mean/peak over allocated nodes."""
    (target,) = load_descriptor(_DESCRIPTORS / "pm100.yml").targets
    raw = tmp_path / "job_table.parquet"
    ts = pa.array([1_600_000_000_000_000] * 2, pa.timestamp("us", tz="UTC"))
    pq.write_table(
        pa.table(
            {
                "job_id": [1, 2],
                "start_time": ts,
                "end_time": ts,
                "submit_time": ts,
                "run_time": [60, 120],
                "num_nodes_alloc": [1, 4],
                "node_power_consumption": pa.array(
                    [[600, 800], [2400, 2800, 3200]], pa.list_(pa.int32())
                ),
            }
        ),
        raw,
    )
    out = tmp_path / "data.parquet"
    normalize_target(raw, target, out)

    rows = pq.read_table(out).to_pylist()
    assert [r["avgpcon_per_node"] for r in rows] == [700.0, 700.0]
    assert [r["maxpcon_per_node"] for r in rows] == [800.0, 800.0]


def test_eagle_average_power_comes_from_node_energy(tmp_path: Path) -> None:
    """Eagle's node_energy_total_watt_hours is the job's energy over all its nodes (#206):
    Wh x 3600 / runtime is the job's average W, / nodes_used per node. 0 Wh is no reading,
    and a job without power keeps its runtime row."""
    (target,) = load_descriptor(_DESCRIPTORS / "nlr_eagle.yml").targets
    assert {"runtime_seconds", "avgpcon_per_node"} <= set(target.target_columns)
    assert "maxpcon_per_node" not in target.target_columns
    # Impossible readings (#216): the outer 0.1% of per-node power, not of whole-job power.
    assert target.mapping["avgpcon_per_node"]["trim_quantiles"] == [0.001, 0.999]
    assert "trim_quantiles" not in target.mapping["avgpcon"]
    start = pa.array([1_717_200_000_000_000] * 4, pa.timestamp("us", tz="UTC"))
    end = pa.array([1_717_203_600_000_000] * 4, pa.timestamp("us", tz="UTC"))  # 1 hour
    raw = tmp_path / "eagle.parquet"
    pq.write_table(
        pa.table(
            {
                "id": [1, 2, 3, 4],
                "submit_time_tz": start,
                "start_time_tz": start,
                "end_time_tz": end,
                "nodes_used": pa.array([2, 1, 1, 4], pa.int64()),
                "node_energy_total_watt_hours": [900.0, 0.0, None, 1600.0],
            }
        ),
        raw,
    )
    out = tmp_path / "data.parquet"
    summary = normalize_target(raw, target, out)

    rows = pq.read_table(out).to_pylist()
    assert summary["rows_final"] == 4
    assert [r["avgpcon"] for r in rows] == [900.0, None, None, 1600.0]
    assert [r["avgpcon_per_node"] for r in rows] == [450.0, None, None, 400.0]


def test_kestrel_average_power_is_null_where_the_node_was_shared(tmp_path: Path) -> None:
    """Slurm's job energy is the node's on a shared node (#209), so a job that shared its
    node (shared_job_count >= 1, or a shared* partition) has no power target. 0 J is no
    reading. Every job keeps its runtime row."""
    (target,) = load_descriptor(_DESCRIPTORS / "nlr_kestrel.yml").targets
    assert {"runtime_seconds", "avgpcon_per_node"} <= set(target.target_columns)
    assert "maxpcon_per_node" not in target.target_columns
    assert target.mapping["avgpcon_per_node"]["trim_quantiles"] == [0.001, 0.999]  # #216
    start = pa.array([1_717_200_000_000_000] * 5, pa.timestamp("us", tz="UTC"))
    end = pa.array([1_717_203_600_000_000] * 5, pa.timestamp("us", tz="UTC"))  # 1 hour
    raw = tmp_path / "kestrel.parquet"
    pq.write_table(
        pa.table(
            {
                "id": ["1", "2", "3", "4", "5"],
                "submit_time": start,
                "start_time": start,
                "end_time": end,
                "nodes_used": pa.array([2, 1, 1, 1, 1], pa.int64()),
                "partition": ["standard", "standard", "shared", "short", "short"],
                "shared_job_count": [None, 1.0, None, None, None],
                "consumed_energy_raw_joules": [
                    3600.0 * 1400,
                    3600.0 * 700,
                    3600.0 * 700,
                    0.0,
                    None,
                ],
            }
        ),
        raw,
    )
    out = tmp_path / "data.parquet"
    summary = normalize_target(raw, target, out)

    rows = pq.read_table(out).to_pylist()
    assert summary["rows_final"] == 5
    assert [r["avgpcon_per_node"] for r in rows] == [700.0, None, None, None, None]
