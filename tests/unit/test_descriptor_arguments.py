"""Commands that take a descriptor also take a bundled dataset's name (#259), and
`recipes write` names the folder its ceilings go to (#259)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from hpc_oda_commons.datasets.descriptor import bundled_descriptor_paths, find_descriptor
from hpc_oda_commons.qst.cli import app

PM100 = bundled_descriptor_paths()["pm100"]


def test_a_name_an_id_or_a_path_finds_the_descriptor() -> None:
    assert find_descriptor("pm100") == PM100
    assert find_descriptor("dataset.pm100") == PM100
    assert find_descriptor("dataset.job_power.pm100") == PM100
    assert find_descriptor(PM100) == PM100
    assert find_descriptor("no_such_dataset") is None


def test_recipes_write_takes_a_dataset_name(tmp_path: Path) -> None:
    out = tmp_path / "recipes"
    result = CliRunner().invoke(app, ["recipes", "write", "dataset.pm100", "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert list((out / "power").glob("*.yml"))


def test_an_unknown_dataset_is_refused() -> None:
    result = CliRunner().invoke(app, ["datasets", "fetch", "no_such_dataset", "--offline"])
    assert result.exit_code != 0
    text = " ".join(result.output.replace("│", " ").split())  # Rich wraps it in a box
    assert "neither a descriptor file nor a bundled dataset" in text


def test_ceilings_go_to_the_folder_the_leaderboard_is_told(tmp_path: Path) -> None:
    out = tmp_path / "recipes"
    result = CliRunner().invoke(
        app,
        ["recipes", "write", "pm100", "--out", str(out), "--benchmark-dir", "my/ceilings"],
    )
    assert result.exit_code == 0, result.output
    text = " ".join(result.output.split())
    assert "--out my/ceilings/pm100." in text
    assert "--ceilings my/ceilings" in text
