from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Optional

import pytest


CLI_EXECUTABLE = os.environ.get("HPC_ODA_CLI", "hpc-oda")


@dataclass(frozen=True)
class CmdResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    def assert_ok(self) -> "CmdResult":
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
    env: Optional[Mapping[str, str]] = None,
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
    )
    return CmdResult(cmd, proc.returncode, proc.stdout, proc.stderr)


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


def load_schema(repo_root: Path, rel: str) -> dict:
    schema_path = repo_root / rel
    if not schema_path.exists():
        raise AssertionError(f"Missing schema file: {schema_path}")
    return load_json(schema_path)


def find_first(path: Path, pattern: str) -> Path:
    matches = list(path.rglob(pattern))
    if not matches:
        raise AssertionError(f"Expected to find {pattern} under {path}, found none.")
    return matches[0]
