"""Reduce job scripts to their *distinguishing* content before embedding.

Most jobs on an HPC cluster are indistinguishable on submission-time prose (on a
representative production slice, ~72% are exact duplicates), which caps accuracy and
creates large neighbour-tie groups. Internal job scripts *do* differentiate otherwise-
identical submissions — but full scripts are mostly shared boilerplate, and their
``#SBATCH`` directives merely restate the prose we already embed. This module keeps only
the part of each script that distinguishes it:

1. **Universal:** drop ``#SBATCH`` directive lines from every script (they duplicate the
   submission-time prose).
2. **Per group of size >= 2** (rows sharing an identical prose serialization): drop lines
   present in *all* members; each row's residual is its remaining lines, original order.
3. **Singletons** (unique prose): the ``#SBATCH``-stripped script, unchanged — there is no
   group to diff against, and the common-line step would erase everything.

The residual then rides the existing ``extra_text_columns`` path, so the final embedded
text is ``prose + residual``. **Security:** script content never leaves this process —
callers must not log residuals or write them to the manifest; only aggregate stats do.
"""

from __future__ import annotations

from dataclasses import dataclass


def strip_sbatch(script: str) -> list[str]:
    """Return the script's lines with ``#SBATCH`` directive lines removed.

    Matches ``#SBATCH`` after optional leading whitespace (the conventional directive
    form); ordinary comments and commands are kept.
    """
    return [line for line in script.splitlines() if not line.lstrip().startswith("#SBATCH")]


@dataclass(frozen=True)
class ResidualStats:
    """Aggregate, content-free summary of a residual pass (safe for the manifest)."""

    rows: int
    groups: int
    singletons: int
    empty_residual_rows: int
    mean_residual_chars: float


def compute_residuals(scripts: list[str], group_keys: list[str]) -> tuple[list[str], ResidualStats]:
    """Reduce each script to its residual relative to its ``group_keys`` group.

    ``scripts[i]`` and ``group_keys[i]`` describe the same row. Rows sharing a key form a
    group; within a group of >= 2, lines present in *every* member are dropped from each
    member (order preserved). Singleton groups keep their ``#SBATCH``-stripped script.

    Returns ``(residuals, stats)``. Deterministic: output depends only on inputs, and each
    row is written by index so group iteration order is irrelevant.
    """
    if len(scripts) != len(group_keys):
        raise ValueError("scripts and group_keys must be the same length")

    bodies = [strip_sbatch(s) for s in scripts]
    groups: dict[str, list[int]] = {}
    for i, key in enumerate(group_keys):
        groups.setdefault(key, []).append(i)

    residuals = [""] * len(scripts)
    singletons = 0
    for idxs in groups.values():
        if len(idxs) == 1:
            singletons += 1
            i = idxs[0]
            residuals[i] = "\n".join(bodies[i])
            continue
        common: set[str] = set(bodies[idxs[0]])
        for i in idxs[1:]:
            common &= set(bodies[i])
            if not common:
                break
        for i in idxs:
            residuals[i] = "\n".join(line for line in bodies[i] if line not in common)

    empty = sum(1 for r in residuals if not r)
    mean_chars = round(sum(len(r) for r in residuals) / len(residuals), 1) if residuals else 0.0
    stats = ResidualStats(
        rows=len(scripts),
        groups=len(groups),
        singletons=singletons,
        empty_residual_rows=empty,
        mean_residual_chars=mean_chars,
    )
    return residuals, stats
