"""Unit tests for the benchmark-matrix orchestration (command building, dep wiring, sacct)."""

from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.benchmarking.hpc.config import SiteConfig
from hpc_oda_commons.benchmarking.hpc.orchestrate import (
    Command,
    LoadedPlan,
    collect_commands,
    parse_sacct,
    remote_mkdirs_command,
    rsync_pull,
    rsync_push,
    run_command,
    sacct_command,
    sbatch_command,
    ssh_command,
    stage_commands,
    submit_plan,
)


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


def test_rsync_push_and_pull_use_host_alias() -> None:
    push = rsync_push(Path("/local/win"), "/base/data/windows", _site(), label="x")
    assert push.argv == ["rsync", "-a", "/local/win/", "mycluster:/base/data/windows/"]
    pull = rsync_pull("/base/runs", Path("/local/runs"), _site(), label="x")
    assert pull.argv == ["rsync", "-a", "mycluster:/base/runs/", "/local/runs/"]


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

    sacct = sacct_command(_site(), ["1", "2", "3"])
    assert "sacct -X -j 1,2,3" in sacct.argv[-1]
    assert "--parsable2" in sacct.argv[-1]


def test_stage_and_collect_commands_shape() -> None:
    plan = _plan()
    stage = stage_commands(
        plan, _site(), windows_dir=Path("/local/win"), plan_dir=Path("/local/p1")
    )
    assert [c.label for c in stage][0] == "mkdir remote dirs"
    assert len(stage) == 3
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
