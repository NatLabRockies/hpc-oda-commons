from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from hpc_oda_commons.kernel.paths import ensure_dir
from hpc_oda_commons.kernel.validate import validate_json, validate_json_file

REQUIRED_FILES = ("result.json", "metrics.json", "provenance.json")


def write_result_bundle(
    bundle_dir: Path,
    *,
    result: dict[str, Any],
    metrics: dict[str, Any],
    provenance: dict[str, Any],
    validate: bool = True,
) -> None:
    ensure_dir(bundle_dir)

    if validate:
        validate_json(result, "oda.result.v0.1.0", path=bundle_dir / "result.json")

    (bundle_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (bundle_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (bundle_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def read_result_bundle(bundle_dir: Path, *, validate: bool = True) -> tuple[dict, dict, dict]:
    result_path = bundle_dir / "result.json"
    metrics_path = bundle_dir / "metrics.json"
    prov_path = bundle_dir / "provenance.json"

    if validate:
        result = validate_json_file(result_path, "oda.result.v0.1.0")
    else:
        result = json.loads(result_path.read_text(encoding="utf-8"))

    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    return result, metrics, prov


def validate_result_bundle(bundle_dir: Path) -> None:
    for fname in REQUIRED_FILES:
        fpath = bundle_dir / fname
        if not fpath.exists():
            raise FileNotFoundError(f"Missing required bundle file: {fpath}")

    validate_json_file(bundle_dir / "result.json", "oda.result.v0.1.0")
