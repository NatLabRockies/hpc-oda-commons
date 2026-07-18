"""Drive a benchmark-matrix plan on the cluster: stage → submit → poll → collect.

Everything host/site-specific comes from :class:`SiteConfig` (loaded from the gitignored
local config); nothing is hardcoded. The command *builders* here are pure functions
returning ``Command`` objects, so the ssh/rsync/sbatch construction and the
embed→``embedding_knn`` dependency wiring are testable without a cluster. A thin executor
runs them, or prints them under dry-run.

Submitting charges the allocation and hits a live cluster, so ``submit`` is dry-run unless
``execute=True``.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from hpc_oda_commons.benchmarking.hpc.config import SiteConfig

_SSH_OPTS = ["-o", "BatchMode=yes"]


class OrchestrationError(RuntimeError):
    """A staged ssh/rsync/sbatch command failed."""


@dataclass
class Command:
    """A single shell command to run locally (ssh/rsync/sbatch all shell out from here)."""

    argv: list[str]
    label: str

    def display(self) -> str:
        return " ".join(shlex.quote(a) for a in self.argv)


@dataclass
class CommandResult:
    ok: bool
    stdout: str = ""
    dry_run: bool = False


# --- pure command builders ----------------------------------------------------------


def ssh_command(site: SiteConfig, remote: str, *, label: str) -> Command:
    return Command(["ssh", *_SSH_OPTS, site.host, remote], label)


def rsync_push(local: Path, remote_path: str, site: SiteConfig, *, label: str) -> Command:
    # trailing slash on source: copy contents, not the dir itself
    src = f"{local}/" if not str(local).endswith("/") else str(local)
    return Command(["rsync", "-a", src, f"{site.host}:{remote_path}/"], label)


def rsync_pull(remote_path: str, local: Path, site: SiteConfig, *, label: str) -> Command:
    return Command(["rsync", "-a", f"{site.host}:{remote_path}/", f"{local}/"], label)


def sbatch_command(
    site: SiteConfig,
    script_remote: str,
    *,
    dependency: str | None = None,
    partition: str | None = None,
    time: str | None = None,
    label: str,
) -> Command:
    """``ssh host 'sbatch --parsable [overrides] <script>'``.

    CLI ``--partition``/``--time`` override the script's ``#SBATCH`` directives (sbatch
    command-line flags win), which is how a quick ``debug``-partition smoke is done.
    """
    parts = ["sbatch", "--parsable"]
    if dependency:
        parts.append(f"--dependency={dependency}")
    if partition:
        parts.append(f"--partition={partition}")
    if time:
        parts.append(f"--time={time}")
    parts.append(script_remote)
    return ssh_command(site, " ".join(parts), label=label)


def remote_mkdirs_command(site: SiteConfig) -> Command:
    dirs = [
        f"{site.repo_dir}/logs",
        f"{site.repo_dir}/data/windows",
        f"{site.repo_dir}/data/embeddings",
        f"{site.repo_dir}/runs",
        site.cache_dir,
    ]
    quoted = " ".join(shlex.quote(d) for d in dirs)
    return ssh_command(site, f"mkdir -p {quoted}", label="mkdir remote dirs")


def sacct_command(site: SiteConfig, jobids: list[str]) -> Command:
    ids = ",".join(jobids)
    remote = f"sacct -X -j {ids} --parsable2 --noheader --format=JobID,State,Elapsed,JobName%60"
    return ssh_command(site, remote, label=f"sacct {len(jobids)} jobs")


# --- executor -----------------------------------------------------------------------


def run_command(cmd: Command, *, execute: bool, echo=print) -> CommandResult:
    """Run ``cmd`` (or print it under dry-run). Raises OrchestrationError on failure."""
    if not execute:
        echo(f"[dry-run] {cmd.label}\n          {cmd.display()}")
        return CommandResult(ok=True, dry_run=True)
    proc = subprocess.run(cmd.argv, capture_output=True, text=True)
    if proc.returncode != 0:
        raise OrchestrationError(
            f"{cmd.label} failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return CommandResult(ok=True, stdout=proc.stdout.strip())


def _parse_jobid(sbatch_stdout: str) -> str:
    # `sbatch --parsable` prints "<jobid>" or "<jobid>;<cluster>"
    return sbatch_stdout.split(";")[0].strip()


# --- plan helpers -------------------------------------------------------------------


@dataclass
class LoadedPlan:
    plan_id: str
    repo_dir: str
    staging_remote: str
    cells: list[dict]
    embeds: list[dict]
    raw: dict = field(default_factory=dict)


def load_plan(plan_path: Path) -> LoadedPlan:
    raw = json.loads(plan_path.read_text(encoding="utf-8"))
    return LoadedPlan(
        plan_id=raw["plan_id"],
        repo_dir=raw["repo_dir"],
        staging_remote=raw["staging_remote"],
        cells=raw.get("cells", []),
        embeds=raw.get("embeds", []),
        raw=raw,
    )


# --- high-level flows ---------------------------------------------------------------


def stage_commands(
    plan: LoadedPlan, site: SiteConfig, *, windows_dir: Path, plan_dir: Path
) -> list[Command]:
    """Remote mkdirs + rsync of sliced windows and the plan dir to the cluster."""
    return [
        remote_mkdirs_command(site),
        rsync_push(
            windows_dir, f"{site.repo_dir}/data/windows", site, label="rsync windowed parquets"
        ),
        rsync_push(plan_dir, plan.staging_remote, site, label="rsync plan (recipes + scripts)"),
    ]


def _filter_cells(plan: LoadedPlan, *, only: str | None, only_model: str | None) -> list[dict]:
    cells = plan.cells
    if only:
        cells = [c for c in cells if c["dataset"] == only]
    if only_model:
        cells = [c for c in cells if c["model"] == only_model]
    return cells


def submit_plan(
    plan: LoadedPlan,
    site: SiteConfig,
    *,
    execute: bool,
    only: str | None = None,
    only_model: str | None = None,
    partition: str | None = None,
    time: str | None = None,
    echo=print,
) -> dict:
    """Submit embeds (for datasets with an included embedding_knn cell), then cells.

    ``embedding_knn`` cells depend on their dataset's embed job (``afterok``). Returns a
    submission manifest. Under dry-run, jobids are placeholders so dependency wiring is
    still visible.
    """
    cells = _filter_cells(plan, only=only, only_model=only_model)
    datasets_needing_embed = {c["dataset"] for c in cells if c.get("needs_embed")}
    embeds = [e for e in plan.embeds if e["dataset"] in datasets_needing_embed]

    embed_jobids: dict[str, str] = {}
    for e in embeds:
        script = f"{plan.staging_remote}/{e['script_path']}"
        cmd = sbatch_command(
            site, script, partition=partition, time=time, label=f"submit embed {e['dataset']}"
        )
        res = run_command(cmd, execute=execute, echo=echo)
        embed_jobids[e["dataset"]] = (
            _parse_jobid(res.stdout) if execute else f"<embed:{e['dataset']}>"
        )

    submitted_cells: list[dict] = []
    for c in cells:
        dep = None
        if c.get("needs_embed"):
            ej = embed_jobids.get(c["dataset"])
            if ej is None:
                echo(f"[warn] no embed job for {c['dataset']}; skipping {c['job_name']}")
                continue
            dep = f"afterok:{ej}"
        script = f"{plan.staging_remote}/{c['script_path']}"
        cmd = sbatch_command(
            site,
            script,
            dependency=dep,
            partition=partition,
            time=time,
            label=f"submit {c['job_name']}",
        )
        res = run_command(cmd, execute=execute, echo=echo)
        jobid = _parse_jobid(res.stdout) if execute else f"<{c['job_name']}>"
        submitted_cells.append(
            {
                "dataset": c["dataset"],
                "model": c["model"],
                "job_name": c["job_name"],
                "jobid": jobid,
                "dependency": dep,
            }
        )

    return {
        "plan_id": plan.plan_id,
        "host": site.host,
        "executed": execute,
        "embeds": embed_jobids,
        "cells": submitted_cells,
    }


def parse_sacct(output: str) -> dict[str, dict[str, str]]:
    """Parse ``sacct --parsable2 --noheader`` (JobID|State|Elapsed|JobName) → {jobid: {...}}."""
    out: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        cols = line.split("|")
        if len(cols) < 2:
            continue
        jobid = cols[0].split(".")[0]  # strip any step suffix defensively
        out[jobid] = {
            "state": cols[1],
            "elapsed": cols[2] if len(cols) > 2 else "",
            "job_name": cols[3] if len(cols) > 3 else "",
        }
    return out


def collect_commands(plan: LoadedPlan, site: SiteConfig, dest: Path) -> list[Command]:
    return [rsync_pull(f"{site.repo_dir}/runs", dest, site, label="rsync results back")]
