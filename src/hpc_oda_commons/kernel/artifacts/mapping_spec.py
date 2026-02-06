from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from hpc_oda_commons.kernel.paths import ensure_parent_dir
from hpc_oda_commons.kernel.validate import SchemaValidationError, validate_json


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def new_mapping_spec(
    *,
    kind: str,
    output_schema_version: str,
    fields: dict[str, Any],
    input: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "oda.mapping.v0.1.0",
        "created_at": _now_utc_iso(),
        "kind": kind,
        "output_schema_version": output_schema_version,
        "input": input or {},
        "fields": fields,
    }


def write_mapping_spec(path: Path, payload: dict[str, Any], *, validate: bool = True) -> None:
    if validate:
        validate_json(payload, "oda.mapping.v0.1.0", path=path)
    ensure_parent_dir(path)
    text = yaml.safe_dump(payload, sort_keys=True, allow_unicode=False)
    path.write_text(text, encoding="utf-8")


def read_mapping_spec(path: Path, *, validate: bool = True) -> dict[str, Any]:
    obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise SchemaValidationError(
            schema_id="oda.mapping.v0.1.0",
            message="Expected a mapping/object at top level.",
            path=str(path),
        )
    if validate:
        validate_json(obj, "oda.mapping.v0.1.0", path=path)
    return obj


def validate_mapping_spec(path: Path) -> dict[str, Any]:
    return read_mapping_spec(path, validate=True)

