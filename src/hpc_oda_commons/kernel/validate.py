from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from jsonschema import Draft202012Validator

from hpc_oda_commons.kernel.schemas import load_schema


class SchemaValidationError(Exception):
    """
    Raised when JSON Schema validation fails.

    NOTE: Do NOT make this a frozen dataclass. Python attaches tracebacks
    to exception instances, and frozen dataclasses can break exception
    propagation (e.g., contextlib/pytest).
    """

    def __init__(self, schema_id: str, message: str, path: str | None = None):
        self.schema_id = schema_id
        self.message = message
        self.path = path
        loc = f" ({path})" if path else ""
        super().__init__(f"{schema_id}{loc}: {message}")


def _format_error(e: Any) -> str:
    loc = "$"
    for p in list(getattr(e, "path", [])):
        loc += f".{p}"
    return f"{loc}: {e.message}"


def validate_json(payload: dict[str, Any], schema_id: str, *, path: Path | None = None) -> None:
    schema = load_schema(schema_id)
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda x: list(x.path))
    if errors:
        lines = ["JSON Schema validation failed:"]
        for err in errors[:20]:
            lines.append(f"- {_format_error(err)}")
        raise SchemaValidationError(
            schema_id=schema_id, message="\n".join(lines), path=str(path) if path else None
        )


def validate_json_file(path: Path, schema_id: str) -> dict[str, Any]:
    payload = path.read_text(encoding="utf-8")
    import json

    obj = json.loads(payload)
    if not isinstance(obj, dict):
        raise SchemaValidationError(
            schema_id=schema_id, message="Expected JSON object at top level.", path=str(path)
        )
    validate_json(obj, schema_id, path=path)
    return obj


def validate_parquet_rows(path: Path, schema_id: str, sample: int = 10) -> None:
    """
    Validate the first N rows of a Parquet file against a JSON Schema (row objects).
    """
    path = Path(path)
    table = pq.read_table(path)
    rows: list[dict[str, Any]] = table.to_pylist()

    if not rows:
        # Up to you: either treat as ok, or error. v0.1 often treats as error.
        raise SchemaValidationError(
            schema_id=schema_id, message="No rows to validate.", path=str(path)
        )

    schema = load_schema(schema_id)
    validator = Draft202012Validator(schema)

    n = min(sample, len(rows))
    for i in range(n):
        row = rows[i]
        errors = sorted(validator.iter_errors(row), key=lambda e: list(e.path))
        if errors:
            lines = [f"Row validation failed (row {i}):"]
            for e in errors[:20]:
                loc = "$" + "".join(f".{p}" for p in list(e.path))
                lines.append(f"- {loc}: {e.message}")
            raise SchemaValidationError(
                schema_id=schema_id, message="\n".join(lines), path=str(path)
            )
