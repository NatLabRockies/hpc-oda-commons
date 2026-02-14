from __future__ import annotations

import importlib
import inspect
import json
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _is_categorical_value(value: Any) -> bool:
    return isinstance(value, (str, bool))


def _normalize_category(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def detect_categorical_columns(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return []

    seen: dict[str, bool] = {}
    for row in rows:
        for key, value in row.items():
            if key not in seen:
                seen[key] = False
            if value is None or value == "":
                continue
            if _is_categorical_value(value):
                seen[key] = True
    return sorted([key for key, is_cat in seen.items() if is_cat])


@dataclass(frozen=True)
class CategoricalFeatureProfile:
    name: str
    row_count: int
    non_null_count: int
    null_count: int
    null_rate: float
    cardinality: int
    top_categories: tuple[tuple[str, int], ...]
    category_counts: tuple[tuple[str, int], ...]
    infrequent_category_count: int
    infrequent_row_fraction: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "row_count": self.row_count,
            "non_null_count": self.non_null_count,
            "null_count": self.null_count,
            "null_rate": self.null_rate,
            "cardinality": self.cardinality,
            "top_categories": [
                {"category": category, "count": count} for category, count in self.top_categories
            ],
            "category_counts": [
                {"category": category, "count": count} for category, count in self.category_counts
            ],
            "infrequent_category_count": self.infrequent_category_count,
            "infrequent_row_fraction": self.infrequent_row_fraction,
        }


def profile_categorical_features(
    rows: list[dict[str, Any]],
    *,
    categorical_columns: list[str] | None = None,
    top_k: int = 10,
    rare_count_threshold: int = 2,
) -> dict[str, CategoricalFeatureProfile]:
    columns = categorical_columns or detect_categorical_columns(rows)
    if not columns:
        return {}

    row_count = len(rows)
    profiles: dict[str, CategoricalFeatureProfile] = {}
    for column in sorted(columns):
        counts: Counter[str] = Counter()
        null_count = 0
        for row in rows:
            normalized = _normalize_category(row.get(column))
            if normalized is None:
                null_count += 1
                continue
            counts[normalized] += 1

        sorted_counts = tuple(sorted(counts.items(), key=lambda item: (-item[1], item[0])))
        non_null_count = sum(count for _, count in sorted_counts)
        cardinality = len(sorted_counts)
        infrequent_rows = sum(count for _, count in sorted_counts if count <= rare_count_threshold)

        profiles[column] = CategoricalFeatureProfile(
            name=column,
            row_count=row_count,
            non_null_count=non_null_count,
            null_count=null_count,
            null_rate=(float(null_count) / float(row_count)) if row_count else 0.0,
            cardinality=cardinality,
            top_categories=sorted_counts[: max(0, top_k)],
            category_counts=sorted_counts,
            infrequent_category_count=sum(
                1 for _, count in sorted_counts if count <= rare_count_threshold
            ),
            infrequent_row_fraction=(
                float(infrequent_rows) / float(non_null_count) if non_null_count else 0.0
            ),
        )

    return profiles


@dataclass(frozen=True)
class OneHotConfig:
    columns: tuple[str, ...]
    min_frequency_count: int
    handle_unknown: str
    estimated_width: int
    category_widths: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": list(self.columns),
            "min_frequency_count": self.min_frequency_count,
            "handle_unknown": self.handle_unknown,
            "estimated_width": self.estimated_width,
            "category_widths": [
                {"column": column, "estimated_width": width}
                for column, width in self.category_widths
            ],
        }


def _estimated_width_for_profile(
    profile: CategoricalFeatureProfile, min_frequency_count: int
) -> int:
    if profile.cardinality == 0:
        return 1 if profile.null_count > 0 else 0

    common = sum(1 for _, count in profile.category_counts if count >= min_frequency_count)
    infrequent = sum(1 for _, count in profile.category_counts if count < min_frequency_count)

    width = common + (1 if infrequent > 0 else 0)
    if profile.null_count > 0:
        width += 1
    return width


def _total_estimated_width(
    profiles: dict[str, CategoricalFeatureProfile],
    columns: tuple[str, ...],
    min_frequency_count: int,
) -> tuple[int, tuple[tuple[str, int], ...]]:
    widths = tuple(
        (column, _estimated_width_for_profile(profiles[column], min_frequency_count))
        for column in columns
    )
    total = sum(width for _, width in widths)
    return total, widths


def select_one_hot_config(
    profiles: dict[str, CategoricalFeatureProfile],
    *,
    infrequent_fraction: float = 0.01,
    min_frequency_floor: int = 2,
    target_max_one_hot_width: int = 2048,
) -> OneHotConfig:
    columns = tuple(sorted(name for name, profile in profiles.items() if profile.cardinality > 0))
    if not columns:
        return OneHotConfig(
            columns=(),
            min_frequency_count=max(1, min_frequency_floor),
            handle_unknown="infrequent_if_exist",
            estimated_width=0,
            category_widths=(),
        )

    max_non_null = max(profiles[column].non_null_count for column in columns)
    if max_non_null <= 0:
        empty_total, empty_widths = _total_estimated_width(
            profiles, columns, max(1, min_frequency_floor)
        )
        return OneHotConfig(
            columns=columns,
            min_frequency_count=max(1, min_frequency_floor),
            handle_unknown="infrequent_if_exist",
            estimated_width=empty_total,
            category_widths=empty_widths,
        )

    start = max(
        min_frequency_floor,
        int(math.ceil(float(max_non_null) * infrequent_fraction)),
        1,
    )
    min_freq = min(start, max_non_null)

    total_width, widths = _total_estimated_width(profiles, columns, min_freq)
    while total_width > target_max_one_hot_width and min_freq < max_non_null:
        min_freq += 1
        total_width, widths = _total_estimated_width(profiles, columns, min_freq)

    while min_freq > max(1, min_frequency_floor):
        candidate = min_freq - 1
        candidate_total, candidate_widths = _total_estimated_width(profiles, columns, candidate)
        if candidate_total > target_max_one_hot_width:
            break
        min_freq = candidate
        total_width, widths = candidate_total, candidate_widths

    return OneHotConfig(
        columns=columns,
        min_frequency_count=min_freq,
        handle_unknown="infrequent_if_exist",
        estimated_width=total_width,
        category_widths=widths,
    )


@dataclass(frozen=True)
class OneHotAnalysis:
    row_count: int
    columns: tuple[str, ...]
    min_frequency_count: int
    encoded_feature_count: int
    category_sizes: tuple[tuple[str, int], ...]
    handle_unknown: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_count": self.row_count,
            "columns": list(self.columns),
            "min_frequency_count": self.min_frequency_count,
            "encoded_feature_count": self.encoded_feature_count,
            "category_sizes": [
                {"column": column, "size": size} for column, size in self.category_sizes
            ],
            "handle_unknown": self.handle_unknown,
        }


def _require_sklearn() -> tuple[Any, Any]:
    try:
        from sklearn.decomposition import TruncatedSVD
        from sklearn.preprocessing import OneHotEncoder
    except Exception as exc:
        raise RuntimeError(
            "Increment 2 preprocessing analysis requires scikit-learn. "
            'Install with `pip install -e ".[dev]"`.'
        ) from exc
    return OneHotEncoder, TruncatedSVD


def _build_one_hot_encoder(min_frequency_count: int, handle_unknown: str) -> Any:
    OneHotEncoder, _ = _require_sklearn()
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


def analyze_one_hot_encoding(
    rows: list[dict[str, Any]],
    config: OneHotConfig,
) -> tuple[OneHotAnalysis, Any]:
    if not config.columns:
        analysis = OneHotAnalysis(
            row_count=len(rows),
            columns=(),
            min_frequency_count=config.min_frequency_count,
            encoded_feature_count=0,
            category_sizes=(),
            handle_unknown=config.handle_unknown,
        )
        return analysis, None

    matrix = [[_normalize_category(row.get(column)) for column in config.columns] for row in rows]
    encoder = _build_one_hot_encoder(config.min_frequency_count, config.handle_unknown)
    encoded = encoder.fit_transform(matrix)

    category_sizes = tuple(
        (column, len(categories))
        for column, categories in zip(config.columns, encoder.categories_, strict=True)
    )

    analysis = OneHotAnalysis(
        row_count=len(rows),
        columns=config.columns,
        min_frequency_count=config.min_frequency_count,
        encoded_feature_count=int(encoded.shape[1]),
        category_sizes=category_sizes,
        handle_unknown=config.handle_unknown,
    )
    return analysis, encoded


@dataclass(frozen=True)
class DimensionalityReductionPlan:
    method: str
    target_coverage: float
    feasible_components: int
    evaluated_components: int
    selected_components: int
    achieved_coverage: float
    variance_ratio_preview: tuple[float, ...]
    cumulative_coverage_preview: tuple[float, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "target_coverage": self.target_coverage,
            "feasible_components": self.feasible_components,
            "evaluated_components": self.evaluated_components,
            "selected_components": self.selected_components,
            "achieved_coverage": self.achieved_coverage,
            "variance_ratio_preview": list(self.variance_ratio_preview),
            "cumulative_coverage_preview": list(self.cumulative_coverage_preview),
        }


def select_svd_components(
    encoded_matrix: Any,
    *,
    target_coverage: float = 0.95,
    max_svd_components: int = 256,
    random_state: int = 42,
) -> DimensionalityReductionPlan:
    target = min(max(float(target_coverage), 0.0), 1.0)

    if encoded_matrix is None:
        return DimensionalityReductionPlan(
            method="truncated_svd",
            target_coverage=target,
            feasible_components=0,
            evaluated_components=0,
            selected_components=0,
            achieved_coverage=1.0,
            variance_ratio_preview=(),
            cumulative_coverage_preview=(),
        )

    _, TruncatedSVD = _require_sklearn()

    n_samples, n_features = encoded_matrix.shape
    feasible = max(0, min(int(n_samples) - 1, int(n_features) - 1))
    if feasible <= 0:
        return DimensionalityReductionPlan(
            method="truncated_svd",
            target_coverage=target,
            feasible_components=feasible,
            evaluated_components=0,
            selected_components=0,
            achieved_coverage=1.0,
            variance_ratio_preview=(),
            cumulative_coverage_preview=(),
        )

    evaluated = min(feasible, max(1, int(max_svd_components)))
    svd = TruncatedSVD(n_components=evaluated, random_state=random_state)
    svd.fit(encoded_matrix)

    ratios = [float(value) for value in svd.explained_variance_ratio_]
    cumulative: list[float] = []
    running = 0.0
    for value in ratios:
        running += value
        cumulative.append(running)

    selected = 0
    for idx, value in enumerate(cumulative, start=1):
        if value >= target:
            selected = idx
            break
    if selected == 0:
        selected = len(cumulative)

    achieved = cumulative[selected - 1] if selected > 0 else 1.0
    preview_len = 25
    return DimensionalityReductionPlan(
        method="truncated_svd",
        target_coverage=target,
        feasible_components=feasible,
        evaluated_components=evaluated,
        selected_components=selected,
        achieved_coverage=float(achieved),
        variance_ratio_preview=tuple(ratios[:preview_len]),
        cumulative_coverage_preview=tuple(cumulative[:preview_len]),
    )


def _library_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for package in ("sklearn", "xgboost", "numpy", "scipy"):
        try:
            module = importlib.import_module(package)
            versions[package] = str(getattr(module, "__version__", "unknown"))
        except Exception:
            versions[package] = "unavailable"
    return versions


def build_preprocessing_diagnostics(
    rows: list[dict[str, Any]],
    *,
    explained_variance_target: float = 0.95,
    infrequent_fraction: float = 0.01,
    min_frequency_floor: int = 2,
    target_max_one_hot_width: int = 2048,
    max_svd_components: int = 256,
    random_state: int = 42,
    categorical_columns: list[str] | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    profiles = profile_categorical_features(
        rows,
        categorical_columns=categorical_columns,
        top_k=top_k,
    )
    one_hot_config = select_one_hot_config(
        profiles,
        infrequent_fraction=infrequent_fraction,
        min_frequency_floor=min_frequency_floor,
        target_max_one_hot_width=target_max_one_hot_width,
    )
    one_hot_analysis, encoded = analyze_one_hot_encoding(rows, one_hot_config)
    svd_plan = select_svd_components(
        encoded,
        target_coverage=explained_variance_target,
        max_svd_components=max_svd_components,
        random_state=random_state,
    )

    return {
        "analysis_version": "job_runtime_xgboost.preprocessing.v0.1.0",
        "row_count": len(rows),
        "library_versions": _library_versions(),
        "categorical_profiles": {
            column: profile.to_dict() for column, profile in sorted(profiles.items())
        },
        "one_hot_config": one_hot_config.to_dict(),
        "one_hot_analysis": one_hot_analysis.to_dict(),
        "dimensionality_reduction": svd_plan.to_dict(),
    }


def write_preprocessing_diagnostics(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
