from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from hpc_oda_commons.kernel.validate import SchemaValidationError, validate_json

RECIPE_SCHEMA_ID = "oda.recipe.v0.1.0"
MDL_SCHEMA_ID = "oda.mdl.v0.1.0"
REQUIRED_METRICS = {"mae", "rmse"}


def load_recipe(recipe_path: Path, *, validate: bool = True) -> dict[str, Any]:
    payload = yaml.safe_load(recipe_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SchemaValidationError(
            schema_id=RECIPE_SCHEMA_ID,
            message="Recipe YAML must be a mapping/object.",
            path=str(recipe_path),
        )
    if validate:
        validate_recipe(payload, path=recipe_path)
    return payload


def validate_recipe(payload: dict[str, Any], *, path: Path | None = None) -> None:
    validate_json(payload, RECIPE_SCHEMA_ID, path=path)

    metrics = payload.get("metrics", [])
    if not isinstance(metrics, list):
        raise SchemaValidationError(
            schema_id=RECIPE_SCHEMA_ID,
            message="metrics must be a list",
            path=str(path) if path else None,
        )

    metric_names: set[str] = set()
    for metric in metrics:
        if not isinstance(metric, dict):
            raise SchemaValidationError(
                schema_id=RECIPE_SCHEMA_ID,
                message="Each metric definition must be an object",
                path=str(path) if path else None,
            )
        validate_json(metric, MDL_SCHEMA_ID, path=path)
        name = str(metric.get("name", ""))
        metric_names.add(name)

    missing = REQUIRED_METRICS - metric_names
    if missing:
        raise SchemaValidationError(
            schema_id=RECIPE_SCHEMA_ID,
            message=f"Missing required metrics: {', '.join(sorted(missing))}",
            path=str(path) if path else None,
        )

    target_fields = {str(m.get("target", "")) for m in metrics}
    if len(target_fields) != 1 or "" in target_fields:
        raise SchemaValidationError(
            schema_id=RECIPE_SCHEMA_ID,
            message="All metrics must share the same non-empty target field.",
            path=str(path) if path else None,
        )
