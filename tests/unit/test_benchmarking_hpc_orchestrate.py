"""Unit tests for the benchmark-matrix orchestration (command building, dep wiring, sacct)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from hpc_oda_commons.benchmarking.hpc import orchestrate
from hpc_oda_commons.benchmarking.hpc.config import SiteConfig
from hpc_oda_commons.benchmarking.hpc.orchestrate import (
    Command,
    LoadedPlan,
    OrchestrationError,
    collect_commands,
    merge_submission_manifest,
    parse_sacct,
    parse_sacct_names,
    parse_sbatch_batch,
    remote_mkdirs_command,
    rsync_pull,
    rsync_push,
    run_command,
    sacct_command,
    sbatch_batch_command,
    sbatch_command,
    ssh_command,
    stage_commands,
    submit_plan,
)
from hpc_oda_commons.qst.commands import bench_matrix


def _site() -> SiteConfig:
    return SiteConfig(
        host="mycluster",
        user="someone",
        account="proj123",
        remote_base="/base",
        env_prefix="/base/env",
        partitions={"cpu": "standard", "bigmem": "bigmem", "gpu": "gpu"},
        gpu_gres="gpu:h100:1",
    )


def _plan() -> LoadedPlan:
    cells = [
        {
            "dataset": "ds",
            "model": "baseline",
            "job_name": "b.ds.baseline",
            "script_path": "scripts/bench__ds__baseline.sbatch",
            "needs_embed": False,
        },
        {
            "dataset": "ds",
            "model": "embedding_knn",
            "job_name": "b.ds.embedding_knn",
            "script_path": "scripts/bench__ds__embedding_knn.sbatch",
            "needs_embed": True,
        },
    ]
    embeds = [{"dataset": "ds", "script_path": "scripts/embed__ds.sbatch", "job_name": "e.ds"}]
    return LoadedPlan(
        plan_id="p1",
        repo_dir="/base/hpc-oda-commons",
        staging_remote="/base/hpc-oda-commons/.hpc_oda/bench-matrix/p1",
        cells=cells,
        embeds=embeds,
    )


# --- command builders ---------------------------------------------------------------


def test_ssh_command_uses_batch_mode_and_host() -> None:
    cmd = ssh_command(_site(), "echo hi", label="x")
    assert cmd.argv == ["ssh", "-o", "BatchMode=yes", "mycluster", "echo hi"]


def test_rsync_push_and_pull_use_host_alias_and_resume_flags() -> None:
    push = rsync_push(Path("/local/win"), "/base/data/windows", _site(), label="x")
    assert push.argv[-2:] == ["/local/win/", "mycluster:/base/data/windows/"]
    assert "--partial" in push.argv and "--timeout=600" in push.argv
    pull = rsync_pull("/base/runs", Path("/local/runs"), _site(), label="x")
    assert pull.argv[-2:] == ["mycluster:/base/runs/", "/local/runs/"]
    assert "--partial" in pull.argv


def test_sbatch_command_plain_and_with_overrides() -> None:
    plain = sbatch_command(_site(), "/r/s.sbatch", label="x")
    assert plain.argv[-1] == "sbatch --parsable /r/s.sbatch"

    dep = sbatch_command(
        _site(),
        "/r/s.sbatch",
        dependency="afterok:42",
        partition="debug",
        time="00:20:00",
        label="x",
    )
    remote = dep.argv[-1]
    assert "--dependency=afterok:42" in remote
    assert "--partition=debug" in remote
    assert "--time=00:20:00" in remote
    assert remote.endswith("/r/s.sbatch")


def test_remote_mkdirs_and_sacct_commands() -> None:
    mk = remote_mkdirs_command(_site())
    assert "mkdir -p" in mk.argv[-1]
    assert "/base/hpc-oda-commons/logs" in mk.argv[-1]
    assert "/base/cache" in mk.argv[-1]
    assert "/base/hf/hub" in mk.argv[-1]  # HF model cache dir

    sacct = sacct_command(_site(), ["1", "2", "3"])
    assert "sacct -X -j 1,2,3" in sacct.argv[-1]
    assert "--parsable2" in sacct.argv[-1]


def test_stage_creates_staging_parent_and_has_three_steps() -> None:
    plan = _plan()
    stage = stage_commands(
        plan, _site(), windows_dir=Path("/local/win"), plan_dir=Path("/local/p1")
    )
    assert [c.label for c in stage][0] == "mkdir remote dirs"
    assert len(stage) == 3
    # the mkdir must include the plan's staging dir (rsync won't create missing parents)
    assert plan.staging_remote in stage[0].argv[-1]
    collect = collect_commands(plan, _site(), Path("/local/out"))
    assert collect[0].argv[0] == "rsync"


# --- run_command (dry-run) ----------------------------------------------------------


def test_run_command_dry_run_does_not_execute() -> None:
    seen: list[str] = []
    res = run_command(Command(["false"], "would fail"), execute=False, echo=seen.append)
    assert res.dry_run and res.ok
    assert any("would fail" in s for s in seen)


# --- submit dependency wiring -------------------------------------------------------


def test_submit_wires_embedding_dependency_only() -> None:
    manifest = submit_plan(_plan(), _site(), execute=False, echo=lambda _s: None)
    by_model = {c["model"]: c for c in manifest["cells"]}
    assert by_model["baseline"]["dependency"] is None
    assert by_model["embedding_knn"]["dependency"] == "afterok:<embed:ds>"
    assert manifest["embeds"] == {"ds": "<embed:ds>"}
    assert manifest["executed"] is False


def test_submit_skips_embed_when_embedding_model_filtered_out() -> None:
    # only baseline requested → no embedding_knn cell → no embed job submitted
    manifest = submit_plan(
        _plan(), _site(), execute=False, only_model="baseline", echo=lambda _s: None
    )
    assert manifest["embeds"] == {}
    assert [c["model"] for c in manifest["cells"]] == ["baseline"]


def test_submit_only_dataset_filter() -> None:
    plan = _plan()
    plan.cells.append(
        {
            "dataset": "other",
            "model": "baseline",
            "job_name": "b.other.baseline",
            "script_path": "scripts/bench__other__baseline.sbatch",
            "needs_embed": False,
        }
    )
    manifest = submit_plan(plan, _site(), execute=False, only="ds", echo=lambda _s: None)
    assert {c["dataset"] for c in manifest["cells"]} == {"ds"}


# --- sacct parsing ------------------------------------------------------------------


def test_parse_sacct_maps_jobid_to_state() -> None:
    out = "101|COMPLETED|00:05:12|b.ds.baseline\n102|FAILED|00:00:03|b.ds.mlp\n\n"
    parsed = parse_sacct(out)
    assert parsed["101"]["state"] == "COMPLETED"
    assert parsed["101"]["elapsed"] == "00:05:12"
    assert parsed["102"]["state"] == "FAILED"


# --- default plan resolution (#147) -------------------------------------------------


def _plan_dir(root: Path, name: str, n_cells: int = 1) -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": name,
                "repo_dir": "/repo",
                "staging_remote": f"/repo/.hpc_oda/bench-matrix/{name}",
                "cells": [{"dataset": "d", "model": "m"}] * n_cells,
                "embeds": [],
            }
        ),
        encoding="utf-8",
    )
    return d


def test_named_plan_does_not_shadow_a_newer_timestamped_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bug: digits sort before letters, so any named plan won every comparison.

    Staging roots accumulate named plans, and `submit` defaults through this helper, so
    the observable failure was launching a stale matrix that produces plausible numbers.
    """
    monkeypatch.setattr(bench_matrix, "_STAGING_ROOT", tmp_path)
    _plan_dir(tmp_path, "test-plan")
    _plan_dir(tmp_path, "fleet-01")
    newest = _plan_dir(tmp_path, "20260820-123449")

    assert bench_matrix._resolve_plan_dir(None) == newest


def test_newest_timestamped_plan_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bench_matrix, "_STAGING_ROOT", tmp_path)
    _plan_dir(tmp_path, "20260718-180141")
    _plan_dir(tmp_path, "20260820-122728")
    newest = _plan_dir(tmp_path, "20260820-123449")

    assert bench_matrix._resolve_plan_dir(None) == newest


def test_a_named_plan_must_be_asked_for_by_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Named plans are never auto-selected — but the error has to say they are there."""
    monkeypatch.setattr(bench_matrix, "_STAGING_ROOT", tmp_path)
    named = _plan_dir(tmp_path, "fleet-01")

    with pytest.raises(typer.Exit):
        bench_matrix._resolve_plan_dir(None)
    # ...and naming it explicitly still works.
    assert bench_matrix._resolve_plan_dir(named) == named


def test_resolve_rejects_a_directory_without_a_plan(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()

    with pytest.raises(typer.Exit):
        bench_matrix._resolve_plan_dir(tmp_path / "empty")


# --- partial submits must not clobber the manifest (#161) -------------------------------


def _manifest(cells, embeds=None, **extra):
    out = {
        "plan_id": "p1",
        "host": "cluster",
        "executed": True,
        "cells": [
            {"dataset": d, "model": m, "job_name": f"b.{d}.{m}", "jobid": j, "dependency": None}
            for d, m, j in cells
        ],
        "embeds": embeds or {},
    }
    out.update(extra)
    return out


def test_a_partial_submit_keeps_the_jobs_it_did_not_touch() -> None:
    """Re-running one failed cell must not erase the record of the other 139 (#161)."""
    fleet = _manifest(
        [("ds_a", "baseline", "1"), ("ds_a", "xgboost", "2"), ("ds_b", "baseline", "3")],
        embeds={"ds_a": "90"},
    )
    repair = _manifest([("ds_a", "xgboost", "999")])

    merged = merge_submission_manifest(fleet, repair)

    assert len(merged["cells"]) == 3
    assert {c["job_name"]: c["jobid"] for c in merged["cells"]} == {
        "b.ds_a.baseline": "1",
        "b.ds_a.xgboost": "999",  # re-submitted: updated, not duplicated
        "b.ds_b.baseline": "3",
    }
    assert merged["embeds"] == {"ds_a": "90"}  # embeds not re-submitted are kept


def test_a_resubmitted_cell_is_updated_not_duplicated() -> None:
    merged = merge_submission_manifest(
        _manifest([("ds", "baseline", "1")]), _manifest([("ds", "baseline", "2")])
    )

    assert len(merged["cells"]) == 1
    assert merged["cells"][0]["jobid"] == "2"


def test_embeds_from_both_submissions_survive() -> None:
    merged = merge_submission_manifest(
        _manifest([], embeds={"ds_a": "10"}), _manifest([], embeds={"ds_b": "20"})
    )

    assert merged["embeds"] == {"ds_a": "10", "ds_b": "20"}


def test_the_first_submission_writes_the_manifest_unchanged() -> None:
    fresh = _manifest([("ds", "baseline", "1")])

    assert merge_submission_manifest(None, fresh) == fresh
    assert merge_submission_manifest({}, fresh) == fresh


def test_top_level_fields_come_from_the_latest_submission() -> None:
    """plan_id and host describe the run; the newest invocation is authoritative."""
    merged = merge_submission_manifest(
        _manifest([("ds", "baseline", "1")], plan_id="old"),
        _manifest([("ds", "xgboost", "2")], plan_id="new"),
    )

    assert merged["plan_id"] == "new"
    assert len(merged["cells"]) == 2


# --- batched, resumable submission (#189) ----------------------------------------------


def _wide_plan(n: int) -> LoadedPlan:
    cells = [
        {
            "dataset": "ds",
            "model": f"m{i}",
            "job_name": f"b.ds.m{i}",
            "script_path": f"scripts/bench__ds__m{i}.sbatch",
            "needs_embed": False,
        }
        for i in range(n)
    ]
    return LoadedPlan(
        plan_id="20260826-231908",
        repo_dir="/base/hpc-oda-commons",
        staging_remote="/base/hpc-oda-commons/.hpc_oda/bench-matrix/p1",
        cells=cells,
        embeds=[],
    )


def test_a_batch_is_one_ssh_for_many_jobs() -> None:
    """The point of batching: 440 round-trips is what made a submit outlast its window."""
    jobs = [(f"b.{i}", f"/s/{i}.sbatch", None) for i in range(20)]
    cmd = sbatch_batch_command(_site(), jobs)
    assert cmd.argv[:4] == ["ssh", "-o", "BatchMode=yes", "mycluster"]
    assert len(cmd.argv) == 5
    assert cmd.argv[4].count("sbatch --parsable") == 20


def test_parse_sbatch_batch_reads_ids_and_strips_the_cluster_suffix() -> None:
    out = "b.a\t123456\nb.b\t123457;cluster\n"
    assert parse_sbatch_batch(out) == {"b.a": "123456", "b.b": "123457"}


def test_parse_sbatch_batch_raises_and_names_the_failures() -> None:
    """An error where a job id belongs would be read downstream as a job that exists."""
    out = "b.a\t123456\nb.b\tsbatch: error: Invalid partition name\n"
    with pytest.raises(OrchestrationError, match="b.b: sbatch: error"):
        parse_sbatch_batch(out)


def test_submit_chunks_the_cells() -> None:
    calls: list[Command] = []

    def _fake_run(cmd, *, execute, echo=print):
        calls.append(cmd)
        names = [frag.split("'")[1] for frag in cmd.argv[4].split("printf '%s\\t' ")[1:]]
        return type(
            "R", (), {"stdout": "".join(f"{n}\t{900 + i}\n" for i, n in enumerate(names))}
        )()

    with patch.object(orchestrate, "run_command", _fake_run):
        manifest = submit_plan(
            _wide_plan(25), _site(), execute=True, chunk_size=10, echo=lambda _s: None
        )

    assert len(calls) == 3  # 10 + 10 + 5
    assert len(manifest["cells"]) == 25


def test_an_interrupted_submit_has_already_recorded_the_batches_that_worked() -> None:
    """The #189 regression guard: the old loop wrote the manifest only at the end."""
    seen: list[int] = []
    calls = {"n": 0}

    def _flaky_run(cmd, *, execute, echo=print):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OrchestrationError("connection dropped")
        names = [frag.split("'")[1] for frag in cmd.argv[4].split("printf '%s\\t' ")[1:]]
        return type(
            "R", (), {"stdout": "".join(f"{n}\t{900 + i}\n" for i, n in enumerate(names))}
        )()

    with patch.object(orchestrate, "run_command", _flaky_run):
        with pytest.raises(OrchestrationError):
            submit_plan(
                _wide_plan(25),
                _site(),
                execute=True,
                chunk_size=10,
                on_progress=lambda m: seen.append(len(m["cells"])),
                echo=lambda _s: None,
            )

    # Two batches landed before the failure, and both were reported as they happened.
    assert seen == [10, 20]


def test_resume_skips_cells_that_already_have_a_job() -> None:
    def _fake_run(cmd, *, execute, echo=print):
        names = [frag.split("'")[1] for frag in cmd.argv[4].split("printf '%s\\t' ")[1:]]
        return type(
            "R", (), {"stdout": "".join(f"{n}\t{900 + i}\n" for i, n in enumerate(names))}
        )()

    with patch.object(orchestrate, "run_command", _fake_run):
        manifest = submit_plan(
            _wide_plan(5),
            _site(),
            execute=True,
            skip_job_names={"b.ds.m0", "b.ds.m3"},
            echo=lambda _s: None,
        )

    assert [c["job_name"] for c in manifest["cells"]] == ["b.ds.m1", "b.ds.m2", "b.ds.m4"]


def test_parse_sacct_names_reads_the_name_column() -> None:
    assert parse_sacct_names("b.a.x|COMPLETED\nb.b.y|RUNNING\n\n") == {"b.a.x", "b.b.y"}


def test_plan_start_date_from_plan_id() -> None:
    assert bench_matrix._plan_start_date("20260826-231908") == "2026-08-26"


def test_plan_start_date_falls_back_wide_when_the_id_carries_no_date() -> None:
    """Over-reporting makes --resume skip visibly; under-reporting duplicates silently."""
    assert bench_matrix._plan_start_date("fleet-01") == "now-30days"
