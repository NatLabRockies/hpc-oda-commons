"""Embedding-based similarity-kNN model for job runtime prediction.

Predicts ``runtime_seconds`` from the k nearest historical jobs in a precomputed
embedding space, under the repo's rolling-window evaluation. Jobs carry a dense
``embedding`` vector (see docs/how-to/embedding-knn.md); the model reuses
``rolling_tabular.split`` for the window schedule and ``kernel.metrics`` for
scoring, and runs an exact per-window dense top-k via ``backends.make_topk``.

Public API:
    evaluate(rows, *, verbose=False, metric_defs=None, capture_artifacts=False) -> dict
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from tqdm import tqdm

from hpc_oda_commons.kernel.metrics import compute_regression_metrics_from_defs
from hpc_oda_commons.models.job_runtime_embedding_knn.backends import (
    make_topk,
    resolve_backend,
    resolve_device,
)
from hpc_oda_commons.models.rolling_tabular.split import build_rolling_splits


@dataclass(frozen=True)
class JobRuntimeEmbeddingKnnConfig:
    """Configuration for the embedding kNN runtime model."""

    n_windows: int = 1000
    test_window_hours: int = 6
    training_lookback_days: int = 100
    submit_time_field: str = "submit_time"
    end_time_field: str = "end_time"
    k: int = 5
    embedding_field: str = "embedding"
    backend: str = "auto"  # auto | numpy | torch | faiss
    device: str = "auto"  # auto | cpu | cuda | mps
    dtype: str = "fp32"  # fp32 | fp16 | bf16
    weighting: str = "similarity"  # similarity | uniform
    normalize: bool = True  # L2-normalize so inner product == cosine
    log_target: bool = False


class JobRuntimeEmbeddingKnnModel:
    """Similarity-weighted embedding kNN with rolling evaluation.

    Public API:
        evaluate(rows, *, verbose=False, metric_defs=None, capture_artifacts=False) -> dict
    """

    _log_prefix = "embedding_knn"
    _evaluate_desc = "rolling/embedding_knn"

    def __init__(self, config: JobRuntimeEmbeddingKnnConfig | None = None) -> None:
        self.config = config or JobRuntimeEmbeddingKnnConfig()
        self.target_field = "runtime_seconds"

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
        metric_defs: list[dict[str, Any]] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        if not rows:
            raise ValueError("rows must be non-empty")

        cfg = self.config
        resolved_metric_defs = metric_defs or [
            {"name": "mae", "target": self.target_field},
            {"name": "rmse", "target": self.target_field},
        ]

        embeddings = self._stack_embeddings(rows)
        targets = self._target_array(rows)

        device = resolve_device(cfg.device)
        backend = resolve_backend(cfg.backend, device)
        if backend == "numpy":
            device = "cpu"  # the numpy engine is always CPU; report it honestly
        topk = make_topk(backend, device, cfg.dtype)
        if verbose:
            print(
                f"[{self._log_prefix}][verbose] backend={backend} device={device} "
                f"dim={embeddings.shape[1]} rows={len(rows)}"
            )

        splits = build_rolling_splits(
            rows,
            n_windows=cfg.n_windows,
            test_window_hours=cfg.test_window_hours,
            training_lookback_days=cfg.training_lookback_days,
            submit_time_field=cfg.submit_time_field,
            end_time_field=cfg.end_time_field,
            verbose=verbose,
        )

        window_entries: list[dict[str, Any]] = []
        all_y_true: list[float] = []
        all_y_pred: list[float] = []

        for split in tqdm(splits, desc=self._evaluate_desc, unit="window", disable=not verbose):
            train_idx = self._supervised_indices(split.train_row_indices, targets)
            test_idx = self._supervised_indices(split.test_row_indices, targets)

            if train_idx.size < 1:
                window_entries.append(self._skip_entry(split, "insufficient_training_rows"))
                continue
            if test_idx.size < 1:
                window_entries.append(self._skip_entry(split, "insufficient_test_rows"))
                continue

            k_eff = min(cfg.k, int(train_idx.size))
            sims, neighbor_cols = topk(embeddings[test_idx], embeddings[train_idx], k_eff)
            weights = self._weights(sims, k_eff)

            neighbor_runtimes = targets[train_idx][neighbor_cols]
            if cfg.log_target:
                neighbor_runtimes = np.log1p(np.maximum(neighbor_runtimes, 0.0))
            preds = (weights * neighbor_runtimes).sum(axis=1)
            if cfg.log_target:
                preds = np.expm1(preds)

            y_true = [float(v) for v in targets[test_idx]]
            y_pred = [float(v) for v in preds]
            metrics = compute_regression_metrics_from_defs(y_true, y_pred, resolved_metric_defs)
            all_y_true.extend(y_true)
            all_y_pred.extend(y_pred)

            if verbose:
                metric_bits = " ".join(f"{k}={metrics[k]:.6f}" for k in sorted(metrics))
                print(
                    f"[{self._log_prefix}][verbose] split={split.split_time_iso} status=ok "
                    f"train={train_idx.size} test={test_idx.size} k={k_eff} {metric_bits}"
                )

            window_entries.append(
                {
                    **split.to_dict(),
                    "status": "ok",
                    "reason": None,
                    "train_rows_supervised": int(train_idx.size),
                    "test_rows_supervised": int(test_idx.size),
                    "k_effective": k_eff,
                    "metrics": metrics,
                }
            )

        if not all_y_true:
            raise ValueError("No rolling splits produced scored predictions.")

        global_metrics = compute_regression_metrics_from_defs(
            all_y_true, all_y_pred, resolved_metric_defs
        )
        windows_scored = sum(1 for e in window_entries if e["status"] == "ok")
        summary = {
            "windows_total": len(splits),
            "windows_scored": windows_scored,
            "windows_skipped": len(splits) - windows_scored,
            "rows_scored": len(all_y_true),
            "backend": backend,
            "device": device,
            "embedding_dim": int(embeddings.shape[1]),
            "n_windows": cfg.n_windows,
            "test_window_hours": cfg.test_window_hours,
            "training_lookback_days": cfg.training_lookback_days,
        }
        if verbose:
            metric_bits = " ".join(f"{k}={global_metrics[k]:.6f}" for k in sorted(global_metrics))
            print(
                f"[{self._log_prefix}][verbose] summary windows_total={summary['windows_total']} "
                f"windows_scored={summary['windows_scored']} rows_scored={summary['rows_scored']} "
                f"{metric_bits}"
            )

        result: dict[str, Any] = {
            **global_metrics,
            "definitions": resolved_metric_defs,
            "windows": window_entries,
            "summary": summary,
        }
        if capture_artifacts:
            result["_y_true"] = all_y_true
            result["_y_pred"] = all_y_pred
            result["_last_model"] = {"kind": self._log_prefix, "config": cfg}
        return result

    # ---- helpers ----

    def _stack_embeddings(self, rows: list[dict[str, Any]]) -> np.ndarray:
        field = self.config.embedding_field
        first = rows[0].get(field)
        if first is None:
            raise ValueError(
                f"rows are missing the embedding field {field!r}; this model needs a dataset "
                "with a precomputed embedding column (see docs/how-to/embedding-knn.md)."
            )
        dim = len(first)
        matrix = np.empty((len(rows), dim), dtype=np.float32)
        for i, row in enumerate(rows):
            vec = row.get(field)
            if vec is None or len(vec) != dim:
                raise ValueError(
                    f"row {i} has a missing or wrong-length embedding "
                    f"(expected dim {dim}) in field {field!r}."
                )
            matrix[i] = vec
        if self.config.normalize:
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            norms[norms == 0.0] = 1.0
            matrix /= norms
        return matrix

    def _target_array(self, rows: list[dict[str, Any]]) -> np.ndarray:
        out = np.full(len(rows), np.nan, dtype=np.float64)
        for i, row in enumerate(rows):
            raw = row.get(self.target_field)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                out[i] = value
        return out

    @staticmethod
    def _supervised_indices(indices: tuple[int, ...], targets: np.ndarray) -> np.ndarray:
        idx = np.asarray(indices, dtype=np.int64)
        if idx.size == 0:
            return idx
        return idx[np.isfinite(targets[idx])]

    def _weights(self, sims: np.ndarray, k_eff: int) -> np.ndarray:
        if self.config.weighting == "uniform":
            return np.full(sims.shape, 1.0 / k_eff, dtype=np.float64)
        clamped = np.maximum(sims, 0.0)
        sums = clamped.sum(axis=1, keepdims=True)
        zero = sums.ravel() == 0.0
        return np.where(zero[:, None], 1.0 / k_eff, clamped / np.where(sums == 0.0, 1.0, sums))

    def _skip_entry(self, split: Any, reason: str) -> dict[str, Any]:
        return {
            **split.to_dict(),
            "status": "skipped",
            "reason": reason,
            "train_rows_supervised": 0,
            "test_rows_supervised": 0,
            "k_effective": 0,
            "metrics": None,
        }
