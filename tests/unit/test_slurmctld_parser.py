from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.adapters.slurmctld.adapter import parse_slurmctld_log


def _write_log(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_parse_slurmctld_single_job(tmp_path: Path) -> None:
    log_path = tmp_path / "slurmctld.log"
    _write_log(
        log_path,
        [
            "[2026-01-01T00:00:00.000] Allocate JobId=10 NodeList=node1 #CPUs=2 Partition=debug",
            "[2026-01-01T00:01:00.000] _job_complete: JobId=10 done",
        ],
    )
    rows = parse_slurmctld_log(log_path)
    assert len(rows) == 1
    assert rows[0]["job_id"] == 10
    assert rows[0]["runtime_seconds"] == 60.0


def test_parse_slurmctld_multiple_jobs(tmp_path: Path) -> None:
    log_path = tmp_path / "slurmctld.log"
    _write_log(
        log_path,
        [
            "[2026-01-01T00:00:00.000] Allocate JobId=1 NodeList=node1 #CPUs=2 Partition=debug",
            "[2026-01-01T00:00:30.000] Allocate JobId=2 NodeList=node2 #CPUs=4 Partition=compute",
            "[2026-01-01T00:01:00.000] _job_complete: JobId=1 done",
            "[2026-01-01T00:03:00.000] _job_complete: JobId=2 done",
        ],
    )
    rows = parse_slurmctld_log(log_path)
    assert {row["job_id"] for row in rows} == {1, 2}
    runtimes = {row["job_id"]: row["runtime_seconds"] for row in rows}
    assert runtimes[1] == 60.0
    assert runtimes[2] == 150.0


def test_parse_slurmctld_skips_incomplete_jobs(tmp_path: Path) -> None:
    log_path = tmp_path / "slurmctld.log"
    _write_log(
        log_path,
        [
            "[2026-01-01T00:00:00.000] Allocate JobId=1 NodeList=node1 #CPUs=2 Partition=debug",
            "[2026-01-01T00:01:00.000] _job_complete: JobId=2 done",
        ],
    )
    rows = parse_slurmctld_log(log_path)
    assert rows == []
