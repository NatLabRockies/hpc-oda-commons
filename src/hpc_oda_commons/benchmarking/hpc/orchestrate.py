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
from collections.abc import Collection, Sequence
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


# --partial keeps partially-transferred files so a dropped large transfer resumes on
# re-run (a single window can be 100s of MB); --timeout avoids an indefinite hang.
_RSYNC_BASE = ["rsync", "-a", "--partial", "--timeout=600"]


def rsync_push(local: Path, remote_path: str, site: SiteConfig, *, label: str) -> Command:
    # trailing slash on source: copy contents, not the dir itself
    src = f"{local}/" if not str(local).endswith("/") else str(local)
    return Command([*_RSYNC_BASE, src, f"{site.host}:{remote_path}/"], label)


def rsync_pull(remote_path: str, local: Path, site: SiteConfig, *, label: str) -> Command:
    return Command([*_RSYNC_BASE, f"{site.host}:{remote_path}/", f"{local}/"], label)


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


# One SSH round-trip costs a second or two. At 440 cells that is the difference between a
# submit that finishes inside an interactive window and one that gets killed partway (#189),
# so cells are submitted in batches: a single remote shell runs many ``sbatch`` calls and
# reports one ``name<TAB>result`` line each.
DEFAULT_SUBMIT_CHUNK = 50


def _sbatch_fragment(
    job_name: str,
    script_remote: str,
    *,
    dependency: str | None,
    partition: str | None,
    time: str | None,
) -> str:
    """One ``sbatch`` inside a batched remote shell, reporting ``name<TAB>result``.

    ``sbatch``'s stderr is folded onto the same line deliberately. A batch must report a
    per-job outcome -- a failure that only showed up as a non-zero exit for the whole batch
    would leave the caller unable to say *which* job did not start.
    """
    parts = ["sbatch", "--parsable"]
    if dependency:
        parts.append(f"--dependency={shlex.quote(dependency)}")
    if partition:
        parts.append(f"--partition={shlex.quote(partition)}")
    if time:
        parts.append(f"--time={shlex.quote(time)}")
    parts.append(shlex.quote(script_remote))
    return (
        f"printf '%s\\t' {shlex.quote(job_name)}; "
        f"{' '.join(parts)} 2>&1 | tr -d '\\n'; printf '\\n'"
    )


def sbatch_batch_command(
    site: SiteConfig,
    jobs: Sequence[tuple[str, str, str | None]],
    *,
    partition: str | None = None,
    time: str | None = None,
) -> Command:
    """One SSH that submits every job in ``jobs`` -- ``(job_name, script_remote, dependency)``."""
    remote = "; ".join(
        _sbatch_fragment(name, script, dependency=dep, partition=partition, time=time)
        for name, script, dep in jobs
    )
    return ssh_command(site, remote, label=f"submit {len(jobs)} job(s)")


def parse_sbatch_batch(output: str) -> dict[str, str]:
    """``name<TAB>result`` lines → ``{job_name: jobid}``.

    A result that is not a job id is an error message from ``sbatch``; it is raised rather
    than stored, because a manifest entry holding an error where a job id belongs would be
    read downstream as a job that exists.
    """
    jobids: dict[str, str] = {}
    failures: list[str] = []
    for line in output.splitlines():
        if "\t" not in line:
            continue
        name, _, result = line.partition("\t")
        result = result.strip()
        # sbatch --parsable prints "<jobid>" or "<jobid>;<cluster>".
        head = result.split(";", 1)[0]
        if head.isdigit():
            jobids[name] = head
        else:
            failures.append(f"{name}: {result or 'no output'}")
    if failures:
        raise OrchestrationError(
            "sbatch failed for "
            + f"{len(failures)} job(s): "
            + "; ".join(failures[:5])
            + (f"; ... and {len(failures) - 5} more" if len(failures) > 5 else "")
        )
    return jobids


def sacct_names_command(site: SiteConfig, *, since: str) -> Command:
    """Every job name this account has run since ``since`` -- the input to ``--resume``."""
    remote = (
        f"sacct -X --starttime {shlex.quote(since)} --parsable2 --noheader "
        "--format=JobName%100,State"
    )
    return ssh_command(site, remote, label=f"sacct job names since {since}")


def parse_sacct_names(output: str) -> set[str]:
    """Job names from ``sacct --parsable2 --noheader --format=JobName,State``."""
    names: set[str] = set()
    for line in output.splitlines():
        name = line.split("|", 1)[0].strip()
        if name:
            names.add(name)
    return names


def remote_mkdirs_command(site: SiteConfig, *, extra: list[str] | None = None) -> Command:
    dirs = [
        f"{site.repo_dir}/logs",
        f"{site.repo_dir}/data/windows",
        f"{site.repo_dir}/data/embeddings",
        f"{site.repo_dir}/runs",
        site.cache_dir,
        f"{site.hf_home}/hub",
        *(extra or []),
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


def merge_submission_manifest(existing: dict | None, fresh: dict) -> dict:
    """Fold this invocation's submissions into whatever the plan already recorded.

    Re-running a cell is the normal repair path -- it is what ``--only`` and ``--only-model``
    exist for -- so a partial submit must not replace the record of the jobs it did not touch.
    Writing ``fresh`` wholesale turned a 140-job manifest into a one-cell file, and ``status``
    reads this file, so it then reported the fleet as one job (#161).

    A re-submitted cell *updates* its entry rather than duplicating it: the new job supersedes
    the old one, which is the behaviour you want when the old one failed.
    """
    if not existing:
        return fresh

    cells = {c["job_name"]: c for c in existing.get("cells", [])}
    cells.update({c["job_name"]: c for c in fresh.get("cells", [])})
    embeds = dict(existing.get("embeds", {}))
    embeds.update(fresh.get("embeds", {}))

    merged = dict(existing)
    merged.update({k: v for k, v in fresh.items() if k not in ("cells", "embeds")})
    merged["cells"] = sorted(cells.values(), key=lambda c: c["job_name"])
    merged["embeds"] = embeds
    return merged


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
    """Remote mkdirs + rsync of sliced windows and the plan dir to the cluster.

    The plan's staging dir is created explicitly: rsync does not create missing destination
    parents, and the cluster's rsync (3.1.3) predates ``--mkpath``.
    """
    return [
        remote_mkdirs_command(site, extra=[plan.staging_remote]),
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


def _submit_batch(
    site: SiteConfig,
    jobs: list[tuple[str, str, str | None]],
    *,
    execute: bool,
    partition: str | None,
    time: str | None,
    echo,
) -> dict[str, str]:
    """Submit a batch and return ``{job_name: jobid}``; placeholders under dry-run."""
    if not execute:
        for name, script, dep in jobs:
            suffix = f" (after {dep})" if dep else ""
            echo(f"[dry-run] submit {name}{suffix}\n          sbatch --parsable {script}")
        return {name: f"<{name}>" for name, _script, _dep in jobs}
    cmd = sbatch_batch_command(site, jobs, partition=partition, time=time)
    res = run_command(cmd, execute=True, echo=echo)
    return parse_sbatch_batch(res.stdout or "")


def submit_plan(
    plan: LoadedPlan,
    site: SiteConfig,
    *,
    execute: bool,
    only: str | None = None,
    only_model: str | None = None,
    partition: str | None = None,
    time: str | None = None,
    chunk_size: int = DEFAULT_SUBMIT_CHUNK,
    skip_job_names: Collection[str] = (),
    on_progress=None,
    echo=print,
) -> dict:
    """Submit embeds (for datasets with an included embedding_knn cell), then cells.

    ``embedding_knn`` cells depend on their dataset's embed job (``afterok``). Returns a
    submission manifest. Under dry-run, jobids are placeholders so dependency wiring is
    still visible.

    Cells go out in batches of ``chunk_size``, one SSH per batch rather than one per cell,
    and ``on_progress`` is called with the manifest-so-far after each batch. At 440 cells the
    old one-SSH-per-cell loop ran long enough to be killed partway, and because the manifest
    was written only at the end it then recorded nothing at all (#189). Both halves matter:
    the batching makes the interruption unlikely, the callback makes it survivable.

    ``skip_job_names`` drops cells that already have a job -- what ``submit --resume`` passes
    after diffing the plan against ``sacct``.
    """
    cells = _filter_cells(plan, only=only, only_model=only_model)
    if skip_job_names:
        skip = set(skip_job_names)
        kept = [c for c in cells if c["job_name"] not in skip]
        if len(kept) != len(cells):
            echo(f"[resume] skipping {len(cells) - len(kept)} cell(s) that already have a job")
        cells = kept
    datasets_needing_embed = {c["dataset"] for c in cells if c.get("needs_embed")}
    embeds = [e for e in plan.embeds if e["dataset"] in datasets_needing_embed]

    embed_jobids: dict[str, str] = {}
    if embeds:
        jobs = [
            (f"embed:{e['dataset']}", f"{plan.staging_remote}/{e['script_path']}", None)
            for e in embeds
        ]
        by_name = _submit_batch(
            site, jobs, execute=execute, partition=partition, time=time, echo=echo
        )
        embed_jobids = {
            e["dataset"]: by_name[f"embed:{e['dataset']}"]
            for e in embeds
            if f"embed:{e['dataset']}" in by_name
        }

    manifest: dict = {
        "plan_id": plan.plan_id,
        "host": site.host,
        "executed": execute,
        "embeds": embed_jobids,
        "cells": [],
    }

    pending: list[dict] = []
    for c in cells:
        dep = None
        if c.get("needs_embed"):
            ej = embed_jobids.get(c["dataset"])
            if ej is None:
                echo(f"[warn] no embed job for {c['dataset']}; skipping {c['job_name']}")
                continue
            dep = f"afterok:{ej}"
        pending.append({**c, "_dependency": dep})

    for i in range(0, len(pending), max(1, chunk_size)):
        batch = pending[i : i + max(1, chunk_size)]
        jobs = [
            (c["job_name"], f"{plan.staging_remote}/{c['script_path']}", c["_dependency"])
            for c in batch
        ]
        by_name = _submit_batch(
            site, jobs, execute=execute, partition=partition, time=time, echo=echo
        )
        for c in batch:
            manifest["cells"].append(
                {
                    "dataset": c["dataset"],
                    "model": c["model"],
                    "job_name": c["job_name"],
                    "jobid": by_name.get(c["job_name"], f"<{c['job_name']}>"),
                    "dependency": c["_dependency"],
                }
            )
        if on_progress is not None:
            # Hand over a copy: the caller persists this, and the next batch mutates ours.
            on_progress({**manifest, "cells": list(manifest["cells"])})

    return manifest


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
