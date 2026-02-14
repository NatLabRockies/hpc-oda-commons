from __future__ import annotations

import importlib.util
import inspect
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from tqdm import tqdm

from hpc_oda_commons.models.job_runtime_xgboost.preprocessing import (
    build_preprocessing_diagnostics,
    detect_categorical_columns,
    profile_categorical_features,
    select_one_hot_config,
    select_svd_components,
    write_preprocessing_diagnostics,
)
from hpc_oda_commons.models.job_runtime_xgboost.split import (
    DailyPreprocessingCache,
    build_hourly_rolling_splits,
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


@dataclass(frozen=True)
class JobRuntimeXGBoostConfig:
    """
    Increment 1 config scaffold for the alternate runtime model.

    Later increments will implement automatic one-hot + dimensionality reduction
    and hourly rolling retraining/evaluation behavior that uses these settings.
    """

    n_recent_hours: int = 1000
    training_lookback_days: int = 100
    submit_time_field: str = "submit_time"
    end_time_field: str = "end_time"
    explained_variance_target: float = 0.98
    infrequent_category_fraction: float = 0.001
    min_frequency_floor: int = 2
    target_max_one_hot_width: int = 2048
    max_svd_components: int = 256
    categorical_top_k: int = 10
    random_state: int = 42

    n_estimators: int = 100
    max_depth: int = 8
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8


class JobRuntimeXGBoostModel:
    """
    Increment 1 scaffold for an alternate runtime prediction model.

    This class intentionally defines the public shape and dependency checks
    without training logic. Training and rolling evaluation are implemented in
    follow-on increments.
    """

    def __init__(self, config: JobRuntimeXGBoostConfig | None = None) -> None:
        self.config = config or JobRuntimeXGBoostConfig()
        self.target_field = "runtime_seconds"

    @staticmethod
    def _check_dependencies() -> None:
        missing: list[str] = []
        for package in ("xgboost", "sklearn"):
            if importlib.util.find_spec(package) is None:
                missing.append(package)
        if missing:
            missing_list = ", ".join(missing)
            raise RuntimeError(
                "Missing optional model dependencies: "
                f'{missing_list}. Install with `pip install -e ".[dev]"`.'
            )

    def fit(self, rows: list[dict[str, Any]]) -> None:
        _ = rows
        self._check_dependencies()
        raise NotImplementedError(
            "JobRuntimeXGBoostModel.fit() is scaffolded in Increment 1. "
            "Training logic lands in later increments."
        )

    def predict(self, rows: list[dict[str, Any]]) -> list[float]:
        _ = rows
        self._check_dependencies()
        raise NotImplementedError(
            "JobRuntimeXGBoostModel.predict() is scaffolded in Increment 1. "
            "Prediction logic lands in later increments."
        )

    def evaluate_hourly(
        self,
        rows: list[dict[str, Any]],
        *,
        verbose: bool = False,
    ) -> dict[str, Any]:
        self._check_dependencies()
        if not rows:
            raise ValueError("rows must be non-empty")

        splits = build_hourly_rolling_splits(
            rows,
            n_recent_hours=self.config.n_recent_hours,
            training_lookback_days=self.config.training_lookback_days,
            submit_time_field=self.config.submit_time_field,
            end_time_field=self.config.end_time_field,
            verbose=verbose,
        )
        cache = self.new_daily_preprocessing_cache()

        hourly_entries: list[dict[str, Any]] = []
        all_y_true: list[float] = []
        all_y_pred: list[float] = []
        preprocessing_refits = 0
        if verbose:
            print(
                "[xgboost][verbose] starting hourly evaluation "
                f"splits={len(splits)} "
                f"n_recent_hours={self.config.n_recent_hours} "
                f"training_lookback_days={self.config.training_lookback_days}"
            )
        split_iter = tqdm(
            splits,
            desc="rolling_hourly/xgboost",
            unit="hour",
            disable=not verbose,
        )

        for split in split_iter:
            train_rows_all, test_rows_all = materialize_split_rows(rows, split)
            train_rows, y_train = self._rows_with_target(train_rows_all)
            test_rows, y_test = self._rows_with_target(test_rows_all)

            if len(train_rows) < 2:
                hourly_entries.append(
                    self._build_skip_entry(
                        split,
                        reason="insufficient_training_rows",
                        preprocessing_refit=False,
                    )
                )
                if verbose:
                    print(
                        "[xgboost][verbose] split="
                        f"{split.split_time_iso} status=skipped "
                        "reason=insufficient_training_rows "
                        f"train={len(train_rows)} test={len(test_rows)}"
                    )
                continue

            artifacts, was_refit = cache.get_or_create(
                split.day_key,
                lambda train_rows=train_rows: self._build_daily_preprocessing_artifacts(train_rows),
            )
            if was_refit:
                preprocessing_refits += 1
                if verbose:
                    print(
                        "[xgboost][verbose] split="
                        f"{split.split_time_iso} preprocessing_refit=True day={split.day_key}"
                    )

            if len(test_rows) < 1:
                hourly_entries.append(
                    self._build_skip_entry(
                        split,
                        reason="insufficient_test_rows",
                        preprocessing_refit=was_refit,
                    )
                )
                if verbose:
                    print(
                        "[xgboost][verbose] split="
                        f"{split.split_time_iso} status=skipped "
                        "reason=insufficient_test_rows "
                        f"train={len(train_rows)} test={len(test_rows)} "
                        f"preprocessing_refit={was_refit}"
                    )
                continue

            x_train = self._transform_rows(train_rows, artifacts)
            x_test = self._transform_rows(test_rows, artifacts)
            if x_train.shape[1] == 0:
                hourly_entries.append(
                    self._build_skip_entry(
                        split,
                        reason="no_features_after_preprocessing",
                        preprocessing_refit=was_refit,
                    )
                )
                if verbose:
                    print(
                        "[xgboost][verbose] split="
                        f"{split.split_time_iso} status=skipped "
                        "reason=no_features_after_preprocessing "
                        f"train={len(train_rows)} test={len(test_rows)} "
                        f"preprocessing_refit={was_refit}"
                    )
                continue

            model = self._new_xgb_regressor()
            model.fit(x_train, y_train)
            pred = model.predict(x_test)
            y_pred = [float(v) for v in pred]
            y_true = [float(v) for v in y_test]
            metrics = self._compute_regression_metrics(y_true, y_pred)
            if verbose:
                print(
                    "[xgboost][verbose] split="
                    f"{split.split_time_iso} status=ok "
                    f"train={len(train_rows)} test={len(test_rows)} "
                    f"preprocessing_refit={was_refit} "
                    f"features={int(x_train.shape[1])} "
                    f"mae={metrics['mae']:.6f} rmse={metrics['rmse']:.6f}"
                )

            all_y_true.extend(y_true)
            all_y_pred.extend(y_pred)

            hourly_entries.append(
                {
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
            )

        if not all_y_true:
            raise ValueError("No hourly splits produced scored predictions.")

        global_metrics = self._compute_regression_metrics(all_y_true, all_y_pred)
        hours_scored = sum(1 for entry in hourly_entries if entry["status"] == "ok")
        summary = {
            "hours_total": len(splits),
            "hours_scored": hours_scored,
            "hours_skipped": len(splits) - hours_scored,
            "preprocessing_refits": preprocessing_refits,
            "rows_scored": len(all_y_true),
            "days_with_cached_preprocessing": list(cache.keys()),
            "n_recent_hours": self.config.n_recent_hours,
            "training_lookback_days": self.config.training_lookback_days,
        }
        if verbose:
            print(
                "[xgboost][verbose] summary "
                f"hours_total={summary['hours_total']} "
                f"hours_scored={summary['hours_scored']} "
                f"hours_skipped={summary['hours_skipped']} "
                f"preprocessing_refits={summary['preprocessing_refits']} "
                f"rows_scored={summary['rows_scored']} "
                f"mae={global_metrics['mae']:.6f} rmse={global_metrics['rmse']:.6f}"
            )

        return {
            **global_metrics,
            "definitions": [
                {"name": "mae", "target": self.target_field},
                {"name": "rmse", "target": self.target_field},
            ],
            "hourly": hourly_entries,
            "summary": summary,
        }

    def build_hourly_split_plan(
        self,
        rows: list[dict[str, Any]],
        *,
        n_recent_hours: int | None = None,
        training_lookback_days: int | None = None,
    ) -> list[dict[str, Any]]:
        split_count = n_recent_hours if n_recent_hours is not None else self.config.n_recent_hours
        lookback_days = (
            training_lookback_days
            if training_lookback_days is not None
            else self.config.training_lookback_days
        )
        splits = build_hourly_rolling_splits(
            rows,
            n_recent_hours=split_count,
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
        """
        Increment 2 analysis helper:
        profile categorical fields, choose one-hot config, and select SVD components.
        """
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

    def _new_xgb_regressor(self) -> Any:
        from xgboost import XGBRegressor

        return XGBRegressor(
            # objective="reg:squarederror",
            # n_estimators=self.config.n_estimators,
            # max_depth=self.config.max_depth,
            # learning_rate=self.config.learning_rate,
            # subsample=self.config.subsample,
            # colsample_bytree=self.config.colsample_bytree,
            random_state=self.config.random_state,
            # n_jobs=1,
            verbosity=0,
        )

    @staticmethod
    def _compute_regression_metrics(y_true: list[float], y_pred: list[float]) -> dict[str, float]:
        if len(y_true) != len(y_pred) or not y_true:
            raise ValueError("y_true and y_pred must be the same non-zero length")
        n = float(len(y_true))
        mae = sum(abs(a - b) for a, b in zip(y_true, y_pred)) / n
        rmse = (sum((a - b) ** 2 for a, b in zip(y_true, y_pred)) / n) ** 0.5
        return {"mae": float(mae), "rmse": float(rmse)}

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
            encoder = self._build_one_hot_encoder(
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

    @staticmethod
    def _normalize_category(value: Any) -> str | None:
        if value is None or value == "":
            return None
        return str(value)

    def _categorical_matrix(
        self, rows: list[dict[str, Any]], columns: tuple[str, ...] | list[str]
    ) -> list[list[str | None]]:
        return [[self._normalize_category(row.get(column)) for column in columns] for row in rows]

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
    def _build_one_hot_encoder(min_frequency_count: int, handle_unknown: str) -> Any:
        from sklearn.preprocessing import OneHotEncoder

        signature = inspect.signature(OneHotEncoder.__init__)
        kwargs: dict[str, Any] = {
            "handle_unknown": handle_unknown,
            "min_frequency": min_frequency_count,
            "dtype": float,
        }
        if "sparse_output" in signature.parameters:
            kwargs["sparse_output"] = True
        else:
            kwargs["sparse"] = True
        return OneHotEncoder(**kwargs)

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
