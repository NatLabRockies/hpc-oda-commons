from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import typer

from hpc_oda_commons.ingest.jobs_parquet.profile import ColumnProfile
from hpc_oda_commons.kernel.artifacts.mapping_spec import new_mapping_spec

REQUIRED_FIELDS = ("job_id", "start_time", "end_time", "runtime_seconds")
OPTIONAL_FIELDS = (
    "submit_time",
    "state",
    "user",
    "account",
    "partition",
    "qos",
    "nodes_requested",
    "memory_requested",
    "processors_requested",
    "gpus_requested",
    "wallclock_requested",
    "name",
    "submit_line",
    "work_dir",
)


def normalize_duration_unit(value: str) -> str:
    raw = value.strip().lower()
    mapping = {
        "s": "seconds",
        "sec": "seconds",
        "secs": "seconds",
        "second": "seconds",
        "seconds": "seconds",
        "m": "minutes",
        "min": "minutes",
        "mins": "minutes",
        "minute": "minutes",
        "minutes": "minutes",
        "h": "hours",
        "hr": "hours",
        "hrs": "hours",
        "hour": "hours",
        "hours": "hours",
        "hh:mm:ss": "hh:mm:ss",
        "h:m:s": "hh:mm:ss",
    }
    if raw in mapping:
        return mapping[raw]
    raise ValueError(f"Unsupported duration unit: {value}")


def normalize_timestamp_format(value: str) -> str:
    raw = value.strip().lower()
    mapping = {
        "iso": "iso8601",
        "iso8601": "iso8601",
        "iso-8601": "iso8601",
        "epoch_s": "epoch_s",
        "epoch_sec": "epoch_s",
        "epoch_seconds": "epoch_s",
        "epoch_ms": "epoch_ms",
        "epoch_millis": "epoch_ms",
        "epoch_us": "epoch_us",
        "epoch_micros": "epoch_us",
    }
    if raw in mapping:
        return mapping[raw]
    raise ValueError(f"Unsupported timestamp format: {value}")


def normalize_memory_unit(value: str) -> str:
    raw = value.strip().lower()
    mapping = {
        "b": "bytes",
        "bytes": "bytes",
        "kb": "kb",
        "mb": "mb",
        "gb": "gb",
        "kib": "kib",
        "mib": "mib",
        "gib": "gib",
    }
    if raw in mapping:
        return mapping[raw]
    raise ValueError(f"Unsupported memory unit: {value}")


def _prompt_column(
    field: str,
    candidates: Iterable[dict[str, Any]],
    available: list[str],
) -> str | None:
    candidate_list = list(candidates)
    default = candidate_list[0]["column"] if candidate_list else ""
    hint = ", ".join(c["column"] for c in candidate_list[:3]) or "none"
    prompt = f"Map field '{field}' to column (suggestions: {hint})"
    value = typer.prompt(prompt, default=default, show_default=bool(default))
    value = value.strip()
    if not value:
        return None
    if value not in available:
        raise typer.BadParameter(f"Unknown column '{value}'. Available: {', '.join(available)}")
    return value


def _prompt_yes_no(prompt: str, default: bool) -> bool:
    default_str = "Y/n" if default else "y/N"
    value = typer.prompt(f"{prompt} [{default_str}]", default="y" if default else "n")
    return value.strip().lower() in ("y", "yes")


def _prompt_duration_unit(field: str) -> str:
    value = typer.prompt(
        (
            f"Unit for '{field}' "
            "(seconds e.g. 3600, minutes e.g. 60, hours e.g. 1.0, HH:MM:SS e.g. 01:00:00)"
        ),
        default="seconds",
    )
    return normalize_duration_unit(value)


def _prompt_timestamp_format(field: str) -> str:
    value = typer.prompt(
        (
            f"Timestamp format for '{field}' "
            "(iso8601 e.g. 2026-01-01T00:00:00Z, "
            "epoch_s e.g. 1735689600, epoch_ms e.g. 1735689600000, "
            "epoch_us e.g. 1735689600000000)"
        ),
        default="iso8601",
    )
    return normalize_timestamp_format(value)


def _prompt_memory_unit(field: str) -> str:
    value = typer.prompt(f"Unit for '{field}' (bytes/KB/MB/GB/KiB/MiB/GiB)", default="MB")
    return normalize_memory_unit(value)


def _prompt_fields_to_hash(
    fields: dict[str, Any],
    *,
    default_hash_identifiers: bool,
) -> None:
    """Prompt user to select fields for identifier hashing. Mutates fields in place."""
    hashable = [
        name
        for name, spec in fields.items()
        if spec.get("source") and not spec.get("transform") and not spec.get("derive")
    ]
    if not hashable:
        return

    defaults = {"user", "account"} if default_hash_identifiers else set()
    default_selection = sorted(name for name in hashable if name in defaults)
    default_display = ", ".join(default_selection) if default_selection else "none"

    typer.echo(f"Fields eligible for identifier hashing: {', '.join(hashable)}")
    raw = typer.prompt(
        "Enter comma-separated field names to hash (or 'none')",
        default=default_display,
    ).strip()

    if raw.lower() == "none":
        return

    selected = {name.strip() for name in raw.split(",") if name.strip()}
    for name in selected:
        if name in fields and name in hashable:
            fields[name]["transform"] = {
                "type": "hash_identifier",
                "salt_env": "HPC_ODA_HASH_SALT",
            }


def build_mapping_spec_interactive(
    profiles: list[ColumnProfile],
    suggestions: dict[str, list[dict[str, Any]]],
    *,
    input_path: Path | None = None,
    default_hash_identifiers: bool = True,
) -> dict[str, Any]:
    available = [p.name for p in profiles]
    fields: dict[str, Any] = {}

    for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
        column = _prompt_column(field, suggestions.get(field, []), available)
        entry: dict[str, Any] = {
            "source": column,
            "role": "required" if field in REQUIRED_FIELDS else "optional",
        }

        if column is None:
            if field == "runtime_seconds":
                if fields.get("start_time", {}).get("source") and fields.get("end_time", {}).get(
                    "source"
                ):
                    entry["derive"] = "end_time - start_time"
            fields[field] = entry
            continue

        if field in ("start_time", "end_time", "submit_time"):
            fmt = _prompt_timestamp_format(field)
            entry["transform"] = {"type": "timestamp", "format": fmt}

        if field in ("runtime_seconds", "wallclock_requested"):
            unit = _prompt_duration_unit(field)
            entry["transform"] = {"type": "duration", "unit": unit}

        if field == "memory_requested":
            unit = _prompt_memory_unit(field)
            entry["transform"] = {"type": "memory", "unit": unit}

        fields[field] = entry

    _prompt_fields_to_hash(fields, default_hash_identifiers=default_hash_identifiers)

    input_payload: dict[str, Any] = {}
    if input_path is not None:
        input_payload["path"] = str(input_path)

    return new_mapping_spec(
        kind="jobs_parquet",
        output_schema_version="oda.job.v0.1.0",
        fields=fields,
        input=input_payload,
    )
