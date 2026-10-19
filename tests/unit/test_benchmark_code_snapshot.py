"""A benchmark bundle records the code the run started with, not the checkout at the end
(#215): a long run can outlast a commit, merge or branch switch."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from hpc_oda_commons.kernel import integrity, provenance
from hpc_oda_commons.qst import cli

_START = ("a" * 64, "1111111aaaaaaa")
_LATER = ("b" * 64, "2222222bbbbbbb")


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _recipe(tmp_path: Path) -> Path:
    table_path = tmp_path / "jobs.parquet"
    rows = [
        {
            "job_id": i,
            "submit_time": _ts(f"2026-01-01T0{i}:05:00Z"),
            "start_time": _ts(f"2026-01-01T0{i}:06:00Z"),
            "end_time": _ts(f"2026-01-01T0{i}:20:00Z"),
            "runtime_seconds": 840.0 + 60 * i,
            "partition": "debug",
        }
        for i in range(1, 5)
    ]
    pq.write_table(pa.Table.from_pylist(rows), table_path)
    recipe_path = tmp_path / "recipe.yml"
    recipe_path.write_text(
        "\n".join(
            [
                "recipe_id: recipe.test.code_snapshot",
                "problem_domain:",
                "  - job-runtime-prediction",
                "schema_version: oda.job.v0.2.0",
                "dataset:",
                "  id: test_dataset",
                f"  table_path: {table_path.as_posix()}",
                "model:",
                "  id: model.job_runtime_baseline",
                '  version: "0.1.0"',
                "metrics:",
                "  - name: mae",
                "    target: runtime_seconds",
                "  - name: rmse",
                "    target: runtime_seconds",
                "split:",
                "  method: fixed",
                "  train_fraction: 0.5",
                "  seed: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return recipe_path


def _checkout(monkeypatch: pytest.MonkeyPatch, *, moves: bool) -> None:
    """Fake the checkout: its first source hash and commit read as _START; when it
    ``moves``, every later read sees _LATER, as if a merge landed mid-run."""
    reads = {"hash": 0, "commit": 0}

    def state(kind: str) -> tuple[str, str]:
        reads[kind] += 1
        return _LATER if moves and reads[kind] > 1 else _START

    monkeypatch.setattr(integrity, "compute_source_hash", lambda: state("hash")[0])
    commit = lambda project_root=None: state("commit")[1]  # noqa: E731
    monkeypatch.setattr(integrity, "git_commit_if_available", commit)
    monkeypatch.setattr(provenance, "git_commit_if_available", commit)


def _bundle(tmp_path: Path) -> dict:
    (bundle,) = [p for p in (tmp_path / "runs").iterdir() if p.is_dir()]
    return json.loads((bundle / "result.json").read_text(encoding="utf-8"))


def test_bundle_keeps_the_code_the_run_started_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _checkout(monkeypatch, moves=True)

    cli.benchmark(_recipe(tmp_path))

    result = _bundle(tmp_path)
    assert result["integrity"]["code_hash"] == _START[0]
    assert result["integrity"]["git_commit"] == _START[1]
    assert result["provenance"]["code"]["source_hash"] == _START[0]
    assert result["provenance"]["code"]["git_commit"] == _START[1]
    assert result["provenance"]["code"]["code_changed_during_run"] is True


def test_bundle_says_when_the_checkout_did_not_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _checkout(monkeypatch, moves=False)

    cli.benchmark(_recipe(tmp_path))

    result = _bundle(tmp_path)
    assert result["provenance"]["code"]["git_commit"] == _START[1]
    assert result["provenance"]["code"]["code_changed_during_run"] is False
