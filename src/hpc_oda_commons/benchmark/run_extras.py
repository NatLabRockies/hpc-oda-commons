"""Optional benchmark artifacts written alongside result bundles."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from hpc_oda_commons.kernel.paths import ensure_dir


@dataclass(frozen=True)
class RunExtras:
    save_predictions: bool = False
    save_model: bool = False


@dataclass(frozen=True)
class BenchmarkArtifacts:
    y_true: list[float] | None = None
    y_pred: list[float] | None = None
    last_model: Any | None = None


def parse_run_extras(recipe_payload: dict[str, Any]) -> RunExtras:
    run = recipe_payload.get("run") or {}
    extras = run.get("extras") or {}
    if not isinstance(extras, dict):
        raise ValueError("recipe.run.extras must be an object")
    return RunExtras(
        save_predictions=bool(extras.get("save_predictions", False)),
        save_model=bool(extras.get("save_model", False)),
    )


def needs_artifact_capture(extras: RunExtras) -> bool:
    return extras.save_predictions or extras.save_model


def pop_eval_artifact_keys(payload: dict[str, Any]) -> BenchmarkArtifacts:
    """Extract artifact fields injected by model.evaluate(); mutates payload in place."""
    y_true = payload.pop("_y_true", None)
    y_pred = payload.pop("_y_pred", None)
    last_model = payload.pop("_last_model", None)
    if y_true is not None and not isinstance(y_true, list):
        raise TypeError("_y_true must be a list when present")
    if y_pred is not None and not isinstance(y_pred, list):
        raise TypeError("_y_pred must be a list when present")
    return BenchmarkArtifacts(y_true=y_true, y_pred=y_pred, last_model=last_model)


def write_run_extras(
    bundle_dir: Path,
    extras: RunExtras,
    artifacts: BenchmarkArtifacts,
) -> list[str]:
    """Write optional extras under a result bundle directory."""
    written: list[str] = []
    has_predictions = bool(artifacts.y_true and artifacts.y_pred)
    if len(artifacts.y_true or []) != len(artifacts.y_pred or []):
        raise ValueError("y_true and y_pred must have the same length")

    if extras.save_predictions:
        if not has_predictions:
            raise ValueError("save_predictions requested but benchmark produced no predictions")
        path = bundle_dir / "predictions.parquet"
        table = pa.Table.from_pydict(
            {"y_true": artifacts.y_true, "y_pred": artifacts.y_pred}
        )
        pq.write_table(table, path)
        written.append("predictions.parquet")

    if extras.save_model:
        if artifacts.last_model is None:
            raise ValueError("save_model requested but benchmark produced no trained model")
        model_dir = bundle_dir / "model"
        ensure_dir(model_dir)
        model_path = model_dir / "last_model.pkl"
        with model_path.open("wb") as handle:
            pickle.dump(artifacts.last_model, handle, protocol=pickle.HIGHEST_PROTOCOL)
        written.append("model/last_model.pkl")

    return written
