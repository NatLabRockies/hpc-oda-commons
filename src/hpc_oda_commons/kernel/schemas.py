from __future__ import annotations

import importlib.resources as ir
import json
from functools import lru_cache
from pathlib import Path


class SchemaNotFoundError(FileNotFoundError):
    def __init__(self, schema_id: str, resolved_path: str) -> None:
        super().__init__(f"Schema not found: {schema_id} (resolved to {resolved_path})")
        self.schema_id = schema_id
        self.resolved_path = resolved_path


def _schema_id_to_relpath(schema_id: str) -> Path:
    """
    Map schema_id like:
      'oda.result.v0.1.0' -> 'schemas/oda/result/v0.1.0.json'
      'oda.job.v0.1.0'    -> 'schemas/oda/job/v0.1.0.json'
      'oda.manifest.v0.1.0' -> 'schemas/oda/manifest/v0.1.0.json'
    """
    parts = schema_id.split(".")
    # Expected: oda.<name>.v<major>.<minor>.<patch> (at least)
    if len(parts) < 3 or parts[0] != "oda":
        raise ValueError(
            f"Invalid schema id '{schema_id}'. Expected format: oda.<name>.v<MAJOR>.<MINOR>.<PATCH>"
        )

    name = parts[1]
    ver_parts = parts[2:]
    if not ver_parts[0].startswith("v"):
        raise ValueError(
            f"Invalid schema id '{schema_id}'. Expected format: oda.<name>.v<MAJOR>.<MINOR>.<PATCH>"
        )

    version = ".".join(ver_parts)  # e.g. 'v0.1.0'
    return Path("schemas") / "oda" / name / f"{version}.json"


def schema_resource_path(schema_id: str) -> Path:
    """
    Returns a Path-like reference to the schema within the installed package.
    """
    rel = _schema_id_to_relpath(schema_id)
    base = ir.files("hpc_oda_commons")
    candidate = base / rel.as_posix()
    if not candidate.is_file():
        raise SchemaNotFoundError(schema_id, str(rel))
    return Path(str(candidate))


@lru_cache(maxsize=128)
def load_schema(schema_id: str) -> dict:
    """
    Load a JSON schema by schema_id from packaged resources.
    Cached for efficiency.
    """
    rel = _schema_id_to_relpath(schema_id)
    base = ir.files("hpc_oda_commons")
    candidate = base / rel.as_posix()
    if not candidate.is_file():
        raise SchemaNotFoundError(schema_id, str(rel))
    text = candidate.read_text(encoding="utf-8")
    return json.loads(text)
