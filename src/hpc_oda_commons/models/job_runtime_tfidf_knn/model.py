"""TF-IDF + kNN model for job runtime prediction with rolling evaluation.

Adapted from raddit prediction_comparison/methods/tfidf_knn.py.
Uses HashingVectorizer + TF-IDF weighting + cosine kNN with an incremental
hash matrix cache for efficient rolling evaluation.
"""

from __future__ import annotations

import math
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
from hpc_oda_commons.models.rolling_tabular.split import (
    build_rolling_splits,
    materialize_split_rows,
)


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
    use_incremental_cache: bool = True
    log_target: bool = False


class JobRuntimeTfidfKnnModel:
    """TF-IDF + kNN model with incremental caching for rolling evaluation.

    Public API:
        evaluate(rows, *, verbose=False) -> dict  -- rolling evaluation
    """

    def __init__(self, config: JobRuntimeTfidfKnnConfig | None = None) -> None:
        self.config = config or JobRuntimeTfidfKnnConfig()
        self.target_field = "runtime_seconds"
        self._text_columns: list[str] | None = None
        self._cached_job_ids: set[Any] | None = None
        self._cached_hash_matrix: sp.csr_matrix | None = None
        self._cached_job_id_list: list[Any] | None = None

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

        resolved_metric_defs = metric_defs or [
            {"name": "mae", "target": self.target_field},
            {"name": "rmse", "target": self.target_field},
        ]

        splits = build_rolling_splits(
            rows,
            n_windows=self.config.n_windows,
            test_window_hours=self.config.test_window_hours,
            training_lookback_days=self.config.training_lookback_days,
            submit_time_field=self.config.submit_time_field,
            end_time_field=self.config.end_time_field,
            verbose=verbose,
        )

        window_entries: list[dict[str, Any]] = []
        all_y_true: list[float] = []
        all_y_pred: list[float] = []
        last_model_state: dict[str, Any] | None = None

        if verbose:
            print(
                "[tfidf_knn][verbose] starting rolling evaluation "
                f"splits={len(splits)} "
                f"n_windows={self.config.n_windows} "
                f"training_lookback_days={self.config.training_lookback_days}"
            )

        split_iter = tqdm(
            splits,
            desc="rolling/tfidf_knn",
            unit="window",
            disable=not verbose,
        )

        for split in split_iter:
            train_rows_all, test_rows_all = materialize_split_rows(rows, split)
            train_rows = self._filter_supervised(train_rows_all)
            test_rows = self._filter_supervised(test_rows_all)

            if len(train_rows) < 2:
                window_entries.append(self._skip_entry(split, "insufficient_training_rows"))
                if verbose:
                    print(
                        f"[tfidf_knn][verbose] split={split.split_time_iso} status=skipped "
                        f"reason=insufficient_training_rows "
                        f"train={len(train_rows)} test={len(test_rows)}"
                    )
                continue

            if len(test_rows) < 1:
                window_entries.append(self._skip_entry(split, "insufficient_test_rows"))
                if verbose:
                    print(
                        f"[tfidf_knn][verbose] split={split.split_time_iso} status=skipped "
                        f"reason=insufficient_test_rows "
                        f"train={len(train_rows)} test={len(test_rows)}"
                    )
                continue

            y_true, y_pred, fit_state = self._fit_predict(
                train_rows, test_rows, capture_state=capture_artifacts
            )
            metrics = compute_regression_metrics_from_defs(y_true, y_pred, resolved_metric_defs)
            all_y_true.extend(y_true)
            all_y_pred.extend(y_pred)
            if capture_artifacts and fit_state is not None:
                fit_state["split_time"] = split.split_time_iso
                last_model_state = fit_state

            if verbose:
                metric_bits = " ".join(f"{k}={metrics[k]:.6f}" for k in sorted(metrics))
                print(
                    f"[tfidf_knn][verbose] split={split.split_time_iso} status=ok "
                    f"train={len(train_rows)} test={len(test_rows)} "
                    f"{metric_bits}"
                )

            window_entries.append(
                {
                    **split.to_dict(),
                    "status": "ok",
                    "reason": None,
                    "train_rows_supervised": len(train_rows),
                    "test_rows_supervised": len(test_rows),
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
            "n_windows": self.config.n_windows,
            "test_window_hours": self.config.test_window_hours,
            "training_lookback_days": self.config.training_lookback_days,
        }

        if verbose:
            metric_bits = " ".join(f"{k}={global_metrics[k]:.6f}" for k in sorted(global_metrics))
            print(
                "[tfidf_knn][verbose] summary "
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

    def _fit_predict(
        self,
        train_rows: list[dict[str, Any]],
        test_rows: list[dict[str, Any]],
        *,
        capture_state: bool = False,
    ) -> tuple[list[float], list[float], dict[str, Any] | None]:
        """Vectorize text, find k nearest neighbors, predict by weighted average."""
        if self._text_columns is None:
            self._text_columns = detect_text_columns(train_rows)

        cfg = self.config
        hasher = HashingVectorizer(
            n_features=cfg.n_hash_features,
            ngram_range=cfg.ngram_range,
            dtype=np.float32,
            alternate_sign=False,
        )

        train_job_ids = [row.get("job_id") for row in train_rows]
        current_ids = set(train_job_ids)

        use_cache = (
            cfg.use_incremental_cache
            and self._cached_job_ids is not None
            and all(jid is not None for jid in train_job_ids)
        )

        if use_cache:
            new_ids = current_ids - self._cached_job_ids
            removed_ids = self._cached_job_ids - current_ids

            if removed_ids:
                keep_mask = np.array([jid not in removed_ids for jid in self._cached_job_id_list])
                self._cached_hash_matrix = self._cached_hash_matrix[keep_mask]
                self._cached_job_id_list = [
                    jid for jid, keep in zip(self._cached_job_id_list, keep_mask) if keep
                ]

            if new_ids:
                new_rows = [r for r in train_rows if r.get("job_id") in new_ids]
                new_texts = build_text_column(new_rows, self._text_columns)
                new_hashed = hasher.transform(new_texts)
                self._cached_hash_matrix = sp.vstack(
                    [self._cached_hash_matrix, new_hashed], format="csr"
                )
                self._cached_job_id_list.extend(r.get("job_id") for r in new_rows)

            self._cached_job_ids = current_ids
            x_train_raw = self._cached_hash_matrix

            # Build target array in cached row order
            target_map = {row.get("job_id"): float(row[self.target_field]) for row in train_rows}
            y_train = np.array(
                [target_map[jid] for jid in self._cached_job_id_list], dtype=np.float64
            )
        else:
            train_texts = build_text_column(train_rows, self._text_columns)
            x_train_raw = hasher.transform(train_texts)
            y_train = np.array([float(r[self.target_field]) for r in train_rows], dtype=np.float64)

            if all(jid is not None for jid in train_job_ids):
                self._cached_job_ids = current_ids
                self._cached_hash_matrix = x_train_raw.copy()
                self._cached_job_id_list = list(train_job_ids)

        # TF-IDF weighting
        tfidf = TfidfTransformer()
        x_train = tfidf.fit_transform(x_train_raw)

        test_texts = build_text_column(test_rows, self._text_columns)
        x_test_raw = hasher.transform(test_texts)
        x_test = tfidf.transform(x_test_raw)

        # kNN search
        k_eff = min(cfg.k, x_train.shape[0])
        nn = NearestNeighbors(metric="cosine", n_jobs=-1)
        nn.fit(x_train)
        distances, indices = nn.kneighbors(x_test, n_neighbors=k_eff)

        # Weighted prediction
        targets = y_train
        if cfg.log_target:
            targets = np.log1p(np.maximum(targets, 0))

        sims = np.maximum(1.0 - distances, 0.0)
        sim_sums = sims.sum(axis=1, keepdims=True)
        zero_mask = sim_sums.ravel() == 0.0
        weights = np.where(zero_mask[:, None], 1.0 / k_eff, sims / sim_sums)
        preds = np.sum(weights * targets[indices], axis=1)

        if cfg.log_target:
            preds = np.expm1(preds)

        y_true = [float(r[self.target_field]) for r in test_rows]
        y_pred = [float(v) for v in preds]
        fit_state: dict[str, Any] | None = None
        if capture_state:
            fit_state = {
                "kind": "job_runtime_tfidf_knn",
                "config": cfg,
                "text_columns": list(self._text_columns or []),
                "hasher": hasher,
                "tfidf": tfidf,
                "nn": nn,
                "y_train": y_train,
                "x_train": x_train,
                "k_effective": k_eff,
                "log_target": cfg.log_target,
            }
        return y_true, y_pred, fit_state

    def _filter_supervised(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep rows with a finite runtime_seconds value."""
        result: list[dict[str, Any]] = []
        for row in rows:
            raw = row.get(self.target_field)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            result.append(row)
        return result

    def _skip_entry(self, split: Any, reason: str) -> dict[str, Any]:
        return {
            **split.to_dict(),
            "status": "skipped",
            "reason": reason,
            "train_rows_supervised": 0,
            "test_rows_supervised": 0,
            "metrics": None,
        }
