"""TF-IDF + kNN model for job runtime prediction with rolling evaluation.

Adapted from raddit prediction_comparison/methods/tfidf_knn.py. Job text is
vectorized once up front with a stateless ``HashingVectorizer`` + TF-IDF weighting
and scored with cosine kNN. Because hashing is stateless, each rolling window is a
self-contained slice of the precomputed hash matrix (no cross-window cache), so the
independent per-window fits can run in parallel across cores via ``window_n_jobs``.
Results are assembled in split order and do not depend on the worker count.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.sparse as sp
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.neighbors import NearestNeighbors
from tqdm import tqdm

from hpc_oda_commons.kernel.metrics import compute_regression_metrics_from_defs
from hpc_oda_commons.models.job_runtime_tfidf_knn.vectorization import (
    build_text_column,
    detect_text_columns,
)
from hpc_oda_commons.models.rolling_tabular.split import build_rolling_splits


def _blas_single_thread() -> Any:
    """Pin native BLAS/OpenMP pools to one thread for the duration of the block, so N
    window worker threads don't oversubscribe cores by each launching a multithreaded
    matmul. Falls back to a no-op if threadpoolctl is unavailable."""
    try:
        from threadpoolctl import threadpool_limits

        return threadpool_limits(limits=1)
    except Exception:
        return nullcontext()


@dataclass(frozen=True)
class JobRuntimeTfidfKnnConfig:
    """Configuration for the TF-IDF + kNN runtime prediction model."""

    n_windows: int = 1000
    test_window_hours: int = 6
    training_lookback_days: int = 100
    submit_time_field: str = "submit_time"
    end_time_field: str = "end_time"
    k: int = 5
    n_hash_features: int = 2**14
    ngram_range: tuple[int, int] = (1, 1)
    log_target: bool = False
    # Number of worker threads for the (independent) per-window fits. 1 = sequential and
    # byte-identical to a single-threaded run; >1 runs windows concurrently with BLAS
    # pinned to one thread per worker. Results do not depend on this value. Named
    # distinctly from any estimator-level ``n_jobs`` so the two parallelism axes stay
    # independent (the per-window kNN query always runs single-threaded).
    window_n_jobs: int = 1


@dataclass
class _WindowResult:
    """One window's outcome, assembled by the driver in split order. Carries the live
    supervised counts so verbose logging is faithful whether the window ran sequentially
    or on a worker thread."""

    entry: dict[str, Any]
    y_true: list[float]
    y_pred: list[float]
    fit_state: dict[str, Any] | None
    n_train: int
    n_test: int


class JobRuntimeTfidfKnnModel:
    """TF-IDF + kNN model with precomputed hashing for rolling evaluation.

    Public API:
        evaluate(rows, *, verbose=False) -> dict  -- rolling evaluation
    """

    _log_prefix = "tfidf_knn"
    _evaluate_desc = "rolling/tfidf_knn"

    def __init__(self, config: JobRuntimeTfidfKnnConfig | None = None) -> None:
        self.config = config or JobRuntimeTfidfKnnConfig()
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

        # Precompute once: stateless hashing over every row + the target array. Each
        # window then works on index slices of these, with no cross-window state, so the
        # per-window fits are independent and order-invariant.
        text_columns = detect_text_columns(rows)
        hash_matrix = self._hash_rows(rows, text_columns)
        targets = self._target_array(rows)

        splits = build_rolling_splits(
            rows,
            n_windows=cfg.n_windows,
            test_window_hours=cfg.test_window_hours,
            training_lookback_days=cfg.training_lookback_days,
            submit_time_field=cfg.submit_time_field,
            end_time_field=cfg.end_time_field,
            verbose=verbose,
        )

        if verbose:
            print(
                f"[{self._log_prefix}][verbose] starting rolling evaluation "
                f"splits={len(splits)} "
                f"n_windows={cfg.n_windows} "
                f"training_lookback_days={cfg.training_lookback_days}"
            )

        n_jobs = max(1, int(cfg.window_n_jobs))
        results: list[_WindowResult | None] = [None] * len(splits)
        if n_jobs == 1:
            for i, split in enumerate(
                tqdm(splits, desc=self._evaluate_desc, unit="window", disable=not verbose)
            ):
                results[i] = self._evaluate_window(
                    split,
                    hash_matrix,
                    targets,
                    text_columns,
                    resolved_metric_defs,
                    capture_artifacts,
                )
        else:
            # The per-window fits are independent; run them across a thread pool with BLAS
            # pinned to one thread per worker so cores aren't oversubscribed.
            with _blas_single_thread(), ThreadPoolExecutor(max_workers=n_jobs) as pool:
                futures = {
                    pool.submit(
                        self._evaluate_window,
                        split,
                        hash_matrix,
                        targets,
                        text_columns,
                        resolved_metric_defs,
                        capture_artifacts,
                    ): i
                    for i, split in enumerate(splits)
                }
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc=self._evaluate_desc,
                    unit="window",
                    disable=not verbose,
                ):
                    results[futures[future]] = future.result()

        # Assemble in split order so metrics, window entries, and verbose logs are
        # deterministic regardless of the order workers finished in.
        window_entries: list[dict[str, Any]] = []
        all_y_true: list[float] = []
        all_y_pred: list[float] = []
        last_model_state: dict[str, Any] | None = None
        for i, split in enumerate(splits):
            res = results[i]
            window_entries.append(res.entry)
            if res.entry["status"] == "ok":
                all_y_true.extend(res.y_true)
                all_y_pred.extend(res.y_pred)
                if capture_artifacts and res.fit_state is not None:
                    res.fit_state["split_time"] = split.split_time_iso
                    last_model_state = res.fit_state
            if verbose:
                self._log_window(split, res)

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
            "n_windows": cfg.n_windows,
            "test_window_hours": cfg.test_window_hours,
            "training_lookback_days": cfg.training_lookback_days,
        }

        if verbose:
            metric_bits = " ".join(f"{k}={global_metrics[k]:.6f}" for k in sorted(global_metrics))
            print(
                f"[{self._log_prefix}][verbose] summary "
                f"windows_total={summary['windows_total']} "
                f"windows_scored={summary['windows_scored']} "
                f"windows_skipped={summary['windows_skipped']} "
                f"rows_scored={summary['rows_scored']} "
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
            result["_last_model"] = last_model_state
        return result

    def _hash_rows(self, rows: list[dict[str, Any]], text_columns: list[str]) -> sp.csr_matrix:
        """Hash every row's text once. ``HashingVectorizer`` is stateless, so slicing this
        matrix by a window's row indices is identical to hashing just those rows."""
        cfg = self.config
        hasher = HashingVectorizer(
            n_features=cfg.n_hash_features,
            ngram_range=cfg.ngram_range,
            dtype=np.float32,
            alternate_sign=False,
        )
        texts = build_text_column(rows, text_columns)
        return hasher.transform(texts).tocsr()

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
        """Row indices (ascending) that carry a finite target, preserving split order."""
        idx = np.asarray(indices, dtype=np.int64)
        if idx.size == 0:
            return idx
        return idx[np.isfinite(targets[idx])]

    def _evaluate_window(
        self,
        split: Any,
        hash_matrix: sp.csr_matrix,
        targets: np.ndarray,
        text_columns: list[str],
        metric_defs: list[dict[str, Any]],
        capture_artifacts: bool,
    ) -> _WindowResult:
        """Evaluate one rolling window. Independent of every other window given the
        precomputed hash matrix and targets, so it is safe to run on a worker thread and
        its result does not depend on execution order."""
        cfg = self.config
        train_idx = self._supervised_indices(split.train_row_indices, targets)
        test_idx = self._supervised_indices(split.test_row_indices, targets)

        if train_idx.size < 2:
            return _WindowResult(
                self._skip_entry(split, "insufficient_training_rows"),
                [],
                [],
                None,
                int(train_idx.size),
                int(test_idx.size),
            )
        if test_idx.size < 1:
            return _WindowResult(
                self._skip_entry(split, "insufficient_test_rows"),
                [],
                [],
                None,
                int(train_idx.size),
                int(test_idx.size),
            )

        x_train_raw = hash_matrix[train_idx]
        x_test_raw = hash_matrix[test_idx]
        y_train = targets[train_idx]

        # TF-IDF weighting is fit per window on that window's training slice (unchanged).
        tfidf = TfidfTransformer()
        x_train = tfidf.fit_transform(x_train_raw)
        x_test = tfidf.transform(x_test_raw)

        # kNN search. n_jobs=1: the window pool supplies the parallelism, so a joblib pool
        # per window would only add dispatch overhead (and warning spam) for a small query.
        k_eff = min(cfg.k, x_train.shape[0])
        nn = NearestNeighbors(metric="cosine", n_jobs=1)
        nn.fit(x_train)
        distances, indices = nn.kneighbors(x_test, n_neighbors=k_eff)

        # Weighted prediction
        neighbor_targets = y_train
        if cfg.log_target:
            neighbor_targets = np.log1p(np.maximum(neighbor_targets, 0))

        sims = np.maximum(1.0 - distances, 0.0)
        sim_sums = sims.sum(axis=1, keepdims=True)
        zero_mask = sim_sums.ravel() == 0.0
        weights = np.where(zero_mask[:, None], 1.0 / k_eff, sims / sim_sums)
        preds = np.sum(weights * neighbor_targets[indices], axis=1)

        if cfg.log_target:
            preds = np.expm1(preds)

        y_true = [float(v) for v in targets[test_idx]]
        y_pred = [float(v) for v in preds]
        metrics = compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)

        entry = {
            **split.to_dict(),
            "status": "ok",
            "reason": None,
            "train_rows_supervised": int(train_idx.size),
            "test_rows_supervised": int(test_idx.size),
            "metrics": metrics,
        }
        fit_state: dict[str, Any] | None = None
        if capture_artifacts:
            fit_state = {
                "kind": "job_runtime_tfidf_knn",
                "config": cfg,
                "text_columns": list(text_columns),
                "tfidf": tfidf,
                "nn": nn,
                "y_train": y_train,
                "x_train": x_train,
                "k_effective": k_eff,
                "log_target": cfg.log_target,
            }
        return _WindowResult(
            entry, y_true, y_pred, fit_state, int(train_idx.size), int(test_idx.size)
        )

    def _log_window(self, split: Any, res: _WindowResult) -> None:
        """Emit the verbose per-window line from an assembled result (preserves the
        sequential output regardless of the worker that produced it)."""
        prefix = self._log_prefix
        entry = res.entry
        if entry["status"] == "skipped":
            print(
                f"[{prefix}][verbose] split={split.split_time_iso} status=skipped "
                f"reason={entry['reason']} "
                f"train={res.n_train} test={res.n_test}"
            )
        else:
            metrics = entry["metrics"]
            metric_bits = " ".join(f"{k}={metrics[k]:.6f}" for k in sorted(metrics))
            print(
                f"[{prefix}][verbose] split={split.split_time_iso} status=ok "
                f"train={res.n_train} test={res.n_test} "
                f"{metric_bits}"
            )

    def _skip_entry(self, split: Any, reason: str) -> dict[str, Any]:
        return {
            **split.to_dict(),
            "status": "skipped",
            "reason": reason,
            "train_rows_supervised": 0,
            "test_rows_supervised": 0,
            "metrics": None,
        }
