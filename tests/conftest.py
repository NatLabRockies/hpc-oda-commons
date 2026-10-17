from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest

CLI_EXECUTABLE = os.environ.get("HPC_ODA_CLI", "hpc-oda")


@dataclass(frozen=True)
class CmdResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    def assert_ok(self) -> CmdResult:
        if self.returncode != 0:
            msg = (
                f"Command failed: {' '.join(self.args)}\n"
                f"returncode={self.returncode}\n"
                f"--- stdout ---\n{self.stdout}\n"
                f"--- stderr ---\n{self.stderr}\n"
            )
            raise AssertionError(msg)
        return self


def run_cli(
    args: Iterable[str],
    cwd: Path,
    env: Mapping[str, str] | None = None,
    timeout_s: int = 120,
) -> CmdResult:
    """
    Run the hpc-oda CLI in a subprocess.
    - Uses HPC_ODA_CLI env var to override executable if needed.
    - Captures stdout/stderr for assertions.
    """
    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    cmd = [CLI_EXECUTABLE, *list(args)]
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        env=full_env,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )
    return CmdResult(cmd, proc.returncode, proc.stdout, proc.stderr)


@pytest.fixture(autouse=True, scope="session")
def _preprocessing_store_outside_the_repo(tmp_path_factory: pytest.TempPathFactory):
    """Keep the benchmark runner's preprocessing store (#213) in a session temp dir.

    Its default is ``.hpc_oda/cache/preprocessing`` under the working directory, which for a
    test run is the repo. Pointing it elsewhere still exercises the store -- CLI subprocesses
    inherit the variable -- without writing to the checkout or reusing a previous session's
    entries.
    """
    name = "HPC_ODA_PREPROCESSING_CACHE"
    previous = os.environ.get(name)
    os.environ[name] = str(tmp_path_factory.mktemp("preprocessing-store"))
    yield
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


@pytest.fixture
def repo_root() -> Path:
    # tests/conftest.py -> tests/ -> repo root
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """
    Creates an isolated temp project directory and returns it.
    Tests run CLI commands with cwd=project_dir to avoid touching the repo.
    """
    project_dir = tmp_path / "hpc_oda_project"
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_first(path: Path, pattern: str) -> Path:
    matches = list(path.rglob(pattern))
    if not matches:
        raise AssertionError(f"Expected to find {pattern} under {path}, found none.")
    return matches[0]


def write_slurmctld_log(path: Path, lines: Iterable[str] | None = None) -> Path:
    """
    Write a minimal slurmctld log for tests. Returns the path.
    """
    if lines is None:
        lines = [
            "[2026-01-01T00:00:00.000] Allocate JobId=1 NodeList=node1 #CPUs=2 Partition=debug",
            "[2026-01-01T00:01:00.000] _job_complete: JobId=1 done",
        ]
    path.write_text("\n".join(list(lines)) + "\n", encoding="utf-8")
    return path
