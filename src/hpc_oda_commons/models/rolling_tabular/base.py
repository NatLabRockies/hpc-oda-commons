"""
Neutral base for rolling-window tabular runtime-prediction models.

Owns the rolling evaluation loop, the OHE+SVD daily-preprocessing machinery, and
the configuration shared by the XGBoost, Random Forest, and MLP models. Concrete
models subclass ``RollingTabularModel`` and supply a regressor via
``_new_regressor()`` (and, if needed, a dependency check).
"""

from __future__ import annotations

import importlib.util
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from tqdm import tqdm

from hpc_oda_commons.kernel.metrics import compute_regression_metrics_from_defs
from hpc_oda_commons.models.rolling_tabular.preprocessing import (
    _build_one_hot_encoder,
    _normalize_category,
    build_preprocessing_diagnostics,
    detect_categorical_columns,
    profile_categorical_features,
    select_one_hot_config,
    select_svd_components,
    write_preprocessing_diagnostics,
)
from hpc_oda_commons.models.rolling_tabular.split import (
    DailyPreprocessingCache,
    build_rolling_splits,
    materialize_split_rows,
)


@dataclass(frozen=True)
class _DailyPreprocessingArtifacts:
    numeric_columns: tuple[str, ...]
    categorical_columns: tuple[str, ...]
    one_hot_min_frequency: int
    one_hot_handle_unknown: str
    encoder: Any | None
    svd: Any | None
    svd_components: int
    svd_coverage: float


@dataclass
class _WindowResult:
    """One window's outcome, assembled by the driver in split order. Carries the
    live supervised counts + refit flag so verbose logging is faithful whether the
    window ran sequentially or on a worker thread."""

    entry: dict[str, Any]
    y_true: list[float]
    y_pred: list[float]
    model: Any | None
    n_train: int
    n_test: int
    was_refit: bool


def _blas_single_thread() -> Any:
    """Pin native BLAS/OpenMP pools to one thread for the duration of the block, so
    N window worker threads don't oversubscribe cores by each launching a
    multithreaded matmul. Falls back to a no-op if threadpoolctl is unavailable."""
    try:
        from threadpoolctl import threadpool_limits

        return threadpool_limits(limits=1)
    except Exception:
        return nullcontext()


@dataclass(frozen=True)
class RollingTabularConfig:
    """
    Shared configuration for rolling tabular runtime-prediction models.

    Controls rolling evaluation windows and categorical preprocessing
    (OHE + SVD). Concrete models subclass this to add regressor hyperparameters.
    """

    n_windows: int = 1000
    test_window_hours: int = 6
    training_lookback_days: int = 100
    submit_time_field: str = "submit_time"
    end_time_field: str = "end_time"
    explained_variance_target: float = 0.95
    infrequent_category_fraction: float = 0.001
    min_frequency_floor: int = 2
    target_max_one_hot_width: int = 2048
    max_svd_components: int = 256
    categorical_top_k: int = 10
    random_state: int = 42
    # Number of worker threads for the (independent) per-window fits. 1 = sequential
    # and byte-identical to a single-threaded run; >1 runs windows concurrently with
    # BLAS pinned to one thread per worker. Results do not depend on this value. Named
    # distinctly from any estimator-level ``n_jobs`` (e.g. Random Forest's) so the two
    # parallelism axes stay independent.
    window_n_jobs: int = 1


class RollingTabularModel:
    """
    Base model: rolling train/test evaluation with daily OHE+SVD preprocessing.

    Public API:
    - evaluate(): rolling train/test evaluation with daily preprocessing cache
    - build_split_plan(): preview split windows without running evaluation
    - analyze_preprocessing(): profile categorical features and preview OHE/SVD config

    Subclasses must implement ``_new_regressor()`` and may override
    ``_check_dependencies()`` and the ``_log_prefix`` / ``_evaluate_desc`` labels.
    """

    _evaluate_desc = "rolling/tabular"
    _log_prefix = "rolling_tabular"

    def __init__(self, config: RollingTabularConfig | None = None) -> None:
        self.config = config or RollingTabularConfig()
        self.target_field = "runtime_seconds"

    @staticmethod
    def _check_dependencies() -> None:
        if importlib.util.find_spec("sklearn") is None:
            raise RuntimeError(
                'Missing optional model dependencies: sklearn. Install with `pip install -e ".[dev]"`.'
            )

    def _new_regressor(self, n_train: int) -> Any:
        raise NotImplementedError("Subclasses must implement _new_regressor().")

    def evaluate(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
        metric_defs: list[dict[str, Any]] | None = None,
        capture_artifacts: bool = False,
    ) -> dict[str, Any]:
        self._check_dependencies()
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
        # Build the day-keyed preprocessing artifacts up front so the window sweep is
        # order-independent (and therefore identical for any n_jobs). refit_ids are the
        # split indices that triggered each day's build — the sequential cache semantics.
        cache, refit_ids = self._precompute_daily_artifacts(rows, splits)

        if verbose:
            print(
                f"[{self._log_prefix}][verbose] starting rolling evaluation "
                f"splits={len(splits)} "
                f"n_windows={self.config.n_windows} "
                f"training_lookback_days={self.config.training_lookback_days}"
            )

        n_jobs = max(1, int(self.config.window_n_jobs))
        results: list[_WindowResult | None] = [None] * len(splits)
        if n_jobs == 1:
            for i, split in enumerate(
                tqdm(splits, desc=self._evaluate_desc, unit="window", disable=not verbose)
            ):
                results[i] = self._evaluate_window(
                    split, rows, cache, refit_ids, i, resolved_metric_defs, capture_artifacts
                )
        else:
            # The per-window fits are independent; run them across a thread pool with
            # BLAS pinned to one thread per worker so cores aren't oversubscribed.
            with _blas_single_thread(), ThreadPoolExecutor(max_workers=n_jobs) as pool:
                futures = {
                    pool.submit(
                        self._evaluate_window,
                        split,
                        rows,
                        cache,
                        refit_ids,
                        i,
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
                if capture_artifacts and res.model is not None:
                    last_model_state = {
                        "kind": self._log_prefix,
                        "split_time": split.split_time_iso,
                        "config": self.config,
                        "preprocessing_artifacts": cache.get(split.day_key),
                        "estimator": res.model,
                    }
            if verbose:
                self._log_window(split, res)

        if not all_y_true:
            raise ValueError("No rolling splits produced scored predictions.")

        global_metrics = self._compute_regression_metrics(
            all_y_true, all_y_pred, resolved_metric_defs
        )
        windows_scored = sum(1 for entry in window_entries if entry["status"] == "ok")
        summary = {
            "windows_total": len(splits),
            "windows_scored": windows_scored,
            "windows_skipped": len(splits) - windows_scored,
            "preprocessing_refits": len(refit_ids),
            "rows_scored": len(all_y_true),
            "days_with_cached_preprocessing": list(cache.keys()),
            "n_windows": self.config.n_windows,
            "test_window_hours": self.config.test_window_hours,
            "training_lookback_days": self.config.training_lookback_days,
        }
        if verbose:
            metric_bits = " ".join(f"{k}={global_metrics[k]:.6f}" for k in sorted(global_metrics))
            print(
                f"[{self._log_prefix}][verbose] summary "
                f"windows_total={summary['windows_total']} "
                f"windows_scored={summary['windows_scored']} "
                f"windows_skipped={summary['windows_skipped']} "
                f"preprocessing_refits={summary['preprocessing_refits']} "
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

    def _precompute_daily_artifacts(
        self, rows: list[dict[str, Any]], splits: list[Any]
    ) -> tuple[DailyPreprocessingCache, set[int]]:
        """Build the day-keyed OHE/SVD artifacts in split order, matching the
        sequential cache exactly: each day's artifact is built from the first split
        (in order) whose supervised training set has >= 2 rows. Returns the populated
        cache and the set of those trigger split indices (``preprocessing_refit`` = True)."""
        cache = self.new_daily_preprocessing_cache()
        refit_ids: set[int] = set()
        built: set[str] = set()
        for i, split in enumerate(splits):
            if split.day_key in built:
                continue
            train_rows_all, _test_rows_all = materialize_split_rows(rows, split)
            train_rows, _y_train = self._rows_with_target(train_rows_all)
            if len(train_rows) < 2:
                continue
            cache.get_or_create(
                split.day_key,
                lambda train_rows=train_rows: self._build_daily_preprocessing_artifacts(train_rows),
            )
            built.add(split.day_key)
            refit_ids.add(i)
        return cache, refit_ids

    def _evaluate_window(
        self,
        split: Any,
        rows: list[dict[str, Any]],
        cache: DailyPreprocessingCache,
        refit_ids: set[int],
        split_index: int,
        resolved_metric_defs: list[dict[str, Any]],
        capture_artifacts: bool,
    ) -> _WindowResult:
        """Evaluate one rolling window. Independent of every other window given the
        precomputed day artifact and a fixed ``random_state``, so it is safe to run
        on a worker thread and its result does not depend on execution order."""
        train_rows_all, test_rows_all = materialize_split_rows(rows, split)
        train_rows, y_train = self._rows_with_target(train_rows_all)
        test_rows, y_test = self._rows_with_target(test_rows_all)

        if len(train_rows) < 2:
            return _WindowResult(
                entry=self._build_skip_entry(
                    split, reason="insufficient_training_rows", preprocessing_refit=False
                ),
                y_true=[],
                y_pred=[],
                model=None,
                n_train=len(train_rows),
                n_test=len(test_rows),
                was_refit=False,
            )

        artifacts = cache.get(split.day_key)
        was_refit = split_index in refit_ids

        if len(test_rows) < 1:
            return _WindowResult(
                entry=self._build_skip_entry(
                    split, reason="insufficient_test_rows", preprocessing_refit=was_refit
                ),
                y_true=[],
                y_pred=[],
                model=None,
                n_train=len(train_rows),
                n_test=len(test_rows),
                was_refit=was_refit,
            )

        x_train = self._transform_rows(train_rows, artifacts)
        x_test = self._transform_rows(test_rows, artifacts)
        if x_train.shape[1] == 0:
            return _WindowResult(
                entry=self._build_skip_entry(
                    split, reason="no_features_after_preprocessing", preprocessing_refit=was_refit
                ),
                y_true=[],
                y_pred=[],
                model=None,
                n_train=len(train_rows),
                n_test=len(test_rows),
                was_refit=was_refit,
            )

        model = self._new_regressor(x_train.shape[0])
        model.fit(x_train, y_train)
        pred = model.predict(x_test)
        y_pred = [float(v) for v in pred]
        y_true = [float(v) for v in y_test]
        metrics = self._compute_regression_metrics(y_true, y_pred, resolved_metric_defs)
        entry = {
            **split.to_dict(),
            "status": "ok",
            "reason": None,
            "preprocessing_refit": was_refit,
            "train_rows_supervised": len(train_rows),
            "test_rows_supervised": len(test_rows),
            "feature_info": {
                "numeric_columns": list(artifacts.numeric_columns),
                "categorical_columns": list(artifacts.categorical_columns),
                "one_hot_min_frequency": artifacts.one_hot_min_frequency,
                "one_hot_handle_unknown": artifacts.one_hot_handle_unknown,
                "svd_components": artifacts.svd_components,
                "svd_coverage": artifacts.svd_coverage,
                "feature_count": int(x_train.shape[1]),
            },
            "metrics": metrics,
        }
        return _WindowResult(
            entry=entry,
            y_true=y_true,
            y_pred=y_pred,
            model=model if capture_artifacts else None,
            n_train=len(train_rows),
            n_test=len(test_rows),
            was_refit=was_refit,
        )

    def _log_window(self, split: Any, res: _WindowResult) -> None:
        """Emit the verbose per-window lines from an assembled result, preserving the
        sequential output (refit line first, then the status line)."""
        prefix = self._log_prefix
        if res.was_refit:
            print(
                f"[{prefix}][verbose] split="
                f"{split.split_time_iso} preprocessing_refit=True day={split.day_key}"
            )
        entry = res.entry
        if entry["status"] == "skipped":
            reason = entry["reason"]
            if reason == "insufficient_training_rows":
                print(
                    f"[{prefix}][verbose] split={split.split_time_iso} status=skipped "
                    f"reason=insufficient_training_rows "
                    f"train={res.n_train} test={res.n_test}"
                )
            elif reason == "insufficient_test_rows":
                print(
                    f"[{prefix}][verbose] split={split.split_time_iso} status=skipped "
                    f"reason=insufficient_test_rows "
                    f"train={res.n_train} test={res.n_test} preprocessing_refit={res.was_refit}"
                )
            else:  # no_features_after_preprocessing
                print(
                    f"[{prefix}][verbose] split={split.split_time_iso} status=skipped "
                    f"reason=no_features_after_preprocessing "
                    f"train={res.n_train} test={res.n_test} preprocessing_refit={res.was_refit}"
                )
        else:
            metrics = entry["metrics"]
            metric_bits = " ".join(f"{k}={metrics[k]:.6f}" for k in sorted(metrics))
            print(
                f"[{prefix}][verbose] split="
                f"{split.split_time_iso} status=ok "
                f"train={res.n_train} test={res.n_test} "
                f"preprocessing_refit={res.was_refit} "
                f"features={entry['feature_info']['feature_count']} "
                f"{metric_bits}"
            )

    def build_split_plan(
        self,
        rows: list[dict[str, Any]],
        *,
        n_windows: int | None = None,
        test_window_hours: int | None = None,
        training_lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        split_count = n_windows if n_windows is not None else self.config.n_windows
        window_hours = (
            test_window_hours if test_window_hours is not None else self.config.test_window_hours
        )
        lookback_days = (
            training_lookback_days
            if training_lookback_days is not None
            else self.config.training_lookback_days
        )
        splits = build_rolling_splits(
            rows,
            n_windows=split_count,
            test_window_hours=window_hours,
            training_lookback_days=lookback_days,
            submit_time_field=self.config.submit_time_field,
            end_time_field=self.config.end_time_field,
            verbose=False,
        )
        return [split.to_dict() for split in splits]

    def analyze_preprocessing(
        self,
        rows: list[dict[str, Any]],
        *,
        diagnostics_path: Path | None = None,
        categorical_columns: list[str] | None = None,
    ) -> dict[str, Any]:
        """Profile categorical fields, choose one-hot config, and select SVD components."""
        payload = build_preprocessing_diagnostics(
            rows,
            explained_variance_target=self.config.explained_variance_target,
            infrequent_fraction=self.config.infrequent_category_fraction,
            min_frequency_floor=self.config.min_frequency_floor,
            target_max_one_hot_width=self.config.target_max_one_hot_width,
            max_svd_components=self.config.max_svd_components,
            random_state=self.config.random_state,
            categorical_columns=categorical_columns,
            top_k=self.config.categorical_top_k,
        )
        if diagnostics_path is not None:
            write_preprocessing_diagnostics(diagnostics_path, payload)
        return payload

    @staticmethod
    def new_daily_preprocessing_cache() -> DailyPreprocessingCache:
        return DailyPreprocessingCache()

    @staticmethod
    def _compute_regression_metrics(
        y_true: list[float],
        y_pred: list[float],
        metric_defs: list[dict[str, Any]],
    ) -> dict[str, float]:
        return compute_regression_metrics_from_defs(y_true, y_pred, metric_defs)

    def _rows_with_target(
        self, rows: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], np.ndarray]:
        filtered_rows: list[dict[str, Any]] = []
        targets: list[float] = []
        for row in rows:
            raw = row.get(self.target_field)
            try:
                value = float(raw)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(value):
                continue
            filtered_rows.append(row)
            targets.append(value)
        return filtered_rows, np.asarray(targets, dtype=float)

    def _build_daily_preprocessing_artifacts(
        self, train_rows: list[dict[str, Any]]
    ) -> _DailyPreprocessingArtifacts:
        excluded = {
            self.target_field,
            self.config.submit_time_field,
            self.config.end_time_field,
            "start_time",
        }

        categorical_candidates = detect_categorical_columns(train_rows)
        categorical_columns = [c for c in categorical_candidates if c not in excluded]
        profiles = profile_categorical_features(
            train_rows,
            categorical_columns=categorical_columns,
            top_k=self.config.categorical_top_k,
        )
        one_hot_config = select_one_hot_config(
            profiles,
            infrequent_fraction=self.config.infrequent_category_fraction,
            min_frequency_floor=self.config.min_frequency_floor,
            target_max_one_hot_width=self.config.target_max_one_hot_width,
        )

        numeric_columns = self._detect_numeric_columns(
            train_rows,
            exclude=excluded | set(one_hot_config.columns),
        )

        encoder: Any | None = None
        svd: Any | None = None
        svd_components = 0
        svd_coverage = 1.0

        if one_hot_config.columns:
            encoder = _build_one_hot_encoder(
                one_hot_config.min_frequency_count,
                one_hot_config.handle_unknown,
            )
            matrix = self._categorical_matrix(train_rows, one_hot_config.columns)
            encoded_train = encoder.fit_transform(matrix)
            svd_plan = select_svd_components(
                encoded_train,
                target_coverage=self.config.explained_variance_target,
                max_svd_components=self.config.max_svd_components,
                random_state=self.config.random_state,
            )
            svd_components = int(svd_plan.selected_components)
            svd_coverage = float(svd_plan.achieved_coverage)
            if svd_components > 0:
                from sklearn.decomposition import TruncatedSVD

                svd = TruncatedSVD(
                    n_components=svd_components, random_state=self.config.random_state
                )
                svd.fit(encoded_train)

        return _DailyPreprocessingArtifacts(
            numeric_columns=tuple(numeric_columns),
            categorical_columns=tuple(one_hot_config.columns),
            one_hot_min_frequency=one_hot_config.min_frequency_count,
            one_hot_handle_unknown=one_hot_config.handle_unknown,
            encoder=encoder,
            svd=svd,
            svd_components=svd_components,
            svd_coverage=svd_coverage,
        )

    def _transform_rows(
        self,
        rows: list[dict[str, Any]],
        artifacts: _DailyPreprocessingArtifacts,
    ) -> np.ndarray:
        numeric = self._numeric_matrix(rows, artifacts.numeric_columns)
        categorical = self._categorical_features(rows, artifacts)
        if numeric.shape[1] == 0 and categorical.shape[1] == 0:
            return np.empty((len(rows), 0), dtype=float)
        if numeric.shape[1] == 0:
            return categorical
        if categorical.shape[1] == 0:
            return numeric
        return np.hstack((numeric, categorical))

    def _categorical_matrix(
        self, rows: list[dict[str, Any]], columns: tuple[str, ...] | list[str]
    ) -> list[list[str | None]]:
        return [[_normalize_category(row.get(column)) for column in columns] for row in rows]

    def _categorical_features(
        self, rows: list[dict[str, Any]], artifacts: _DailyPreprocessingArtifacts
    ) -> np.ndarray:
        if not artifacts.categorical_columns or artifacts.encoder is None:
            return np.empty((len(rows), 0), dtype=float)

        matrix = self._categorical_matrix(rows, artifacts.categorical_columns)
        encoded = artifacts.encoder.transform(matrix)
        if artifacts.svd is None or artifacts.svd_components <= 0:
            return np.empty((len(rows), 0), dtype=float)
        transformed = artifacts.svd.transform(encoded)
        return np.asarray(transformed, dtype=float)

    @staticmethod
    def _is_numeric_value(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    def _detect_numeric_columns(
        self, rows: list[dict[str, Any]], *, exclude: set[str]
    ) -> list[str]:
        if not rows:
            return []

        seen_numeric: dict[str, bool] = {}
        invalid: set[str] = set()
        for row in rows:
            for key, value in row.items():
                if key in exclude:
                    continue
                if key not in seen_numeric:
                    seen_numeric[key] = False
                if value is None or value == "":
                    continue
                if self._is_numeric_value(value):
                    seen_numeric[key] = True
                else:
                    invalid.add(key)
        return sorted(
            [key for key, has_numeric in seen_numeric.items() if has_numeric and key not in invalid]
        )

    @staticmethod
    def _numeric_matrix(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> np.ndarray:
        if not columns:
            return np.empty((len(rows), 0), dtype=float)

        out = np.zeros((len(rows), len(columns)), dtype=float)
        for i, row in enumerate(rows):
            for j, col in enumerate(columns):
                raw = row.get(col)
                if raw is None or raw == "":
                    out[i, j] = 0.0
                    continue
                try:
                    out[i, j] = float(raw)
                except (TypeError, ValueError):
                    out[i, j] = 0.0
        return out

    @staticmethod
    def _build_skip_entry(split: Any, *, reason: str, preprocessing_refit: bool) -> dict[str, Any]:
        return {
            **split.to_dict(),
            "status": "skipped",
            "reason": reason,
            "preprocessing_refit": preprocessing_refit,
            "train_rows_supervised": 0,
            "test_rows_supervised": 0,
            "feature_info": None,
            "metrics": None,
        }
