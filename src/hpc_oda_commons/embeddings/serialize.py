"""Serialize a job row into a text description for embedding.

Two formats (`prose`, `kv`), both restricted to **submission-time** information — the
serializer emits an *allowlist* of fields known when the job was submitted and refuses
target/post-hoc fields (runtime, end/start time, state, actual usage). Embedding those
would leak the prediction target, so exclusion is enforced, not just conventional. The
format + included fields are versioned so runs are comparable/reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Submission-time concepts, in a fixed order. Each maps to candidate source columns
# (first present wins), so one policy works across dataset schemas.
_SUBMIT_TIME_CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("job name", ("job_name", "name")),
    ("partition", ("partition",)),
    ("queue", ("queue", "qos")),
    ("account", ("account",)),
    ("user", ("user",)),
    ("science field", ("science_field", "science_field_short")),
    ("machine", ("machine", "machine_name")),
    (
        "requested walltime",
        ("requested_seconds", "wallclock_requested", "wallclock_requested_seconds"),
    ),
    ("requested nodes", ("num_nodes_req", "nodes_requested")),
    ("requested cores", ("num_cores_req", "processors_requested")),
    ("requested gpus", ("num_gpus_req", "gpus_requested")),
    ("requested memory", ("memory_requested", "mem_req")),
)

# Fields that must NEVER be embedded — the target and post-hoc (known only after the
# job ran) values. Requesting any of these (incl. as an extra column) is an error.
FORBIDDEN_FIELDS: frozenset[str] = frozenset(
    {
        "runtime_seconds",
        "run_time",
        "end_time",
        "start_time",
        "state",
        "job_state",
        "exit_status",
        "elapsed",
        "allocated_cpus",
        "num_nodes_alloc",
        "num_cores_alloc",
        "cores_used",
        "nodes_used",
    }
)


class LeakageError(ValueError):
    """Raised when a serialization request would embed a target/post-hoc field."""


@dataclass(frozen=True)
class EmbedConfig:
    """Configuration for turning a job row into embeddable text."""

    text_format: str = "prose"  # prose | kv
    format_version: str = "v1"
    submit_time_field: str = "submit_time"
    include_submit_time_feature: bool = True  # weekday + hour bucket
    extra_text_columns: tuple[str, ...] = ()  # user-added local columns (e.g. job script)
    extra_char_limit: int = 2000  # per-column truncation for extra columns
    instruction: str = ""  # optional model instruction (empty = embed as document)

    def __post_init__(self) -> None:
        if self.text_format not in ("prose", "kv"):
            raise ValueError(f"text_format must be 'prose' or 'kv', got {self.text_format!r}")
        bad = sorted(set(self.extra_text_columns) & FORBIDDEN_FIELDS)
        if bad:
            raise LeakageError(
                f"extra_text_columns includes target/post-hoc field(s) {bad}; embedding these "
                "would leak the prediction target."
            )


def included_fields(config: EmbedConfig, columns: list[str]) -> list[str]:
    """Return the human labels that will appear, given the available columns."""
    labels = [label for label, cands in _SUBMIT_TIME_CONCEPTS if any(c in columns for c in cands)]
    if config.include_submit_time_feature and config.submit_time_field in columns:
        labels.append("submitted")
    labels.extend(config.extra_text_columns)
    return labels


def _value(row: dict, candidates: tuple[str, ...]) -> object | None:
    for col in candidates:
        v = row.get(col)
        if v not in (None, ""):
            return v
    return None


def _submit_feature(row: dict, config: EmbedConfig) -> str | None:
    v = row.get(config.submit_time_field)
    if isinstance(v, datetime):
        return v.strftime("%A %H:00")
    return None


def serialize_row(row: dict, config: EmbedConfig) -> str:
    """Serialize one job row to embeddable text per the configured format."""
    pairs: list[tuple[str, str]] = []
    for label, candidates in _SUBMIT_TIME_CONCEPTS:
        v = _value(row, candidates)
        if v is not None:
            pairs.append((label, str(v)))
    if config.include_submit_time_feature:
        sf = _submit_feature(row, config)
        if sf is not None:
            pairs.append(("submitted", sf))

    extras: list[tuple[str, str]] = []
    for col in config.extra_text_columns:
        v = row.get(col)
        if v not in (None, ""):
            extras.append((col, str(v)[: config.extra_char_limit]))

    text = (
        _render_prose(pairs, extras) if config.text_format == "prose" else _render_kv(pairs, extras)
    )
    if config.instruction:
        text = f"Instruct: {config.instruction}\nQuery: {text}"
    return text


def _render_kv(pairs: list[tuple[str, str]], extras: list[tuple[str, str]]) -> str:
    lines = [f"{label}: {value}" for label, value in pairs]
    for name, value in extras:
        lines.append(f"{name}:\n{value}")
    return "\n".join(lines)


def _render_prose(pairs: list[tuple[str, str]], extras: list[tuple[str, str]]) -> str:
    d = dict(pairs)
    s = "An HPC batch job"
    if "job name" in d:
        s += f" named {d['job name']}"
    if "partition" in d:
        s += f" on the {d['partition']} partition"
    if "queue" in d:
        s += f" (queue {d['queue']})"
    reqs = [
        f"{d[k]} {unit}"
        for k, unit in (
            ("requested nodes", "nodes"),
            ("requested cores", "cores"),
            ("requested gpus", "GPUs"),
            ("requested memory", "memory"),
        )
        if k in d
    ]
    if "requested walltime" in d:
        reqs.append(f"a walltime limit of {d['requested walltime']}")
    if reqs:
        s += ", requesting " + ", ".join(reqs)
    if "account" in d:
        s += f", charged to account {d['account']}"
    if "user" in d:
        s += f", submitted by {d['user']}"
    if "science field" in d:
        s += f", in {d['science field']}"
    if "machine" in d:
        s += f", on {d['machine']}"
    if "submitted" in d:
        s += f", submitted on {d['submitted']}"
    s += "."
    for name, value in extras:
        s += f" {name}:\n{value}"
    return s


def serialize_rows(rows: list[dict], config: EmbedConfig) -> list[str]:
    return [serialize_row(row, config) for row in rows]
