from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import run_cli


@pytest.mark.integration
def test_leaderboard_generation(tmp_project: Path, repo_root: Path) -> None:
    run_cli(["init"], cwd=tmp_project).assert_ok()

    recipe = repo_root / "src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml"
    assert recipe.exists(), f"Missing recipe: {recipe}"

    run_cli(
        ["benchmark", str(recipe)],
        cwd=tmp_project,
        env={"HPC_ODA_OFFLINE": "1"},
        timeout_s=300,
    ).assert_ok()

    run_cli(
        ["leaderboard", "--runs", "runs", "--out", "leaderboard"],
        cwd=tmp_project,
        timeout_s=120,
    ).assert_ok()

    out_dir = tmp_project / "leaderboard"
    assert (out_dir / "leaderboard.json").exists()
    assert (out_dir / "index.html").exists()
