"""Ranking training-lookback arms without letting the ranking see the test set (#190).

Since #187 every ``(dataset, model)`` pair is benchmarked at several training lookbacks, so a
leaderboard row has to pick one. Reporting whichever arm scored best selects on the number it
then reports. That is not a rounding error: with three arms, a model whose arms differ only by
noise gets three draws at the minimum, so best-of-three flatters it while a model whose arms
genuinely agree gains nothing. The leaderboard reorders by variance rather than by skill.

Walk-forward selection removes the leak. The windows are ordered in time, so for each window
past a burn-in the arm is chosen from strictly earlier windows and graded on the current one.
What gets reported is the error of a *policy* -- "use whichever lookback has served best so
far" -- rather than the error of an arm chosen with hindsight. A wrong pick costs exactly what
it costs instead of being edited out, and the policy is one an operator could actually run,
since it never consults a window it has not already lived through.

``oracle_score`` is reported alongside: the best single arm on the same windows, which is what
the naive rule would have published. The gap between the two *is* the selection bias, made
visible rather than argued about.

All of this is arithmetic over metrics already on disk. Pooling a bundle's per-window values
weighted by row count reproduces its global metric bit-for-bit, so nothing here needs a cell
re-run.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

DEFAULT_BURN_IN = 20
DEFAULT_METRIC = "mae"

# A metric is only recoverable from per-window values when it is a row-weighted power mean:
#
#     pooled = (sum_w n_w * v_w**p / sum_w n_w) ** (1/p)
#
# MAE is the p=1 case, RMSE the p=2 case, and ``underprediction_ratio`` is a percentage of
# rows, so p=1 again. ``r2`` and ``mape`` are deliberately absent. r2 is normalised by the
# variance of the window it was measured on, and mape divides by a per-window count that
# excludes zero targets -- pooling either from window values yields a number that is not the
# metric. They raise rather than quietly producing one.
_POOLING_EXPONENT: dict[str, int] = {
    "mae": 1,
    "rmse": 2,
    "underprediction_ratio": 1,
}


class ArmSelectionError(ValueError):
    """The arms cannot be compared as given."""


# Knobs that change how a run executes but not what it computes. If two bundles differ only
# here they are the same configuration measured twice, not two arms -- so they are excluded
# before deciding what distinguishes a cell's bundles. (``window_n_jobs`` can shift a metric
# in the last decimals through float summation order; see docs/known-issues.md #2. That is a
# reproducibility caveat, not an axis worth ranking.)
EXECUTION_ONLY_KNOBS: frozenset[str] = frozenset({"window_n_jobs", "verbose", "n_jobs"})


def derive_arm_keys(configs: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Label each bundle by whatever distinguishes it from the others in its cell (#197).

    The arm key used to be the training lookback, because that was the one axis the recipe id
    spelled out. Deriving it from the recorded configurations instead means any axis works --
    a target-encoding threshold, an objective, a decay rate -- without teaching this function
    about it.

    Raises when the configurations are indistinguishable. Two bundles that ran the same
    configuration are a cell measured twice, and ranking them as arms would report a
    difference that is noise by construction.
    """
    if not configs:
        raise ArmSelectionError("no configurations to key")
    keys = sorted({k for c in configs for k in c} - EXECUTION_ONLY_KNOBS)
    differing = [k for k in keys if len({_stable(c.get(k)) for c in configs}) > 1]
    if not differing:
        raise ArmSelectionError(
            "bundles are configured identically, so they are one cell measured "
            f"{len(configs)} times rather than {len(configs)} arms"
        )
    return tuple("+".join(f"{k}={_stable(c.get(k))}" for k in differing) for c in configs)


def compact_arm_label(arm_key: str) -> str:
    """A short form for display: the values alone when a cell varies along one axis.

    The stored key names its axis (``training_lookback_days=120``) so an artifact is
    self-describing. A console table repeating that name once per arm per row is not, so the
    name is dropped where there is only one axis to confuse it with.
    """
    fields = arm_key.split("+")
    if len(fields) == 1:
        return fields[0].partition("=")[2] or arm_key
    return arm_key


def _stable(value: Any) -> str:
    """A comparable, printable form for a config value of any shape."""
    if isinstance(value, float) and value.is_integer():
        # 30.0 and 30 are the same arm; rendering them differently would split it in two.
        return str(int(value))
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable(v) for v in value) + "]"
    if isinstance(value, Mapping):
        return "{" + ",".join(f"{k}:{_stable(v)}" for k, v in sorted(value.items())) + "}"
    return str(value)


@dataclass(frozen=True)
class Arm:
    """One benchmark cell's per-window record: a model on a dataset at one lookback."""

    key: str
    windows: tuple[dict[str, Any], ...]

    @classmethod
    def from_metrics(cls, key: str, metrics: dict[str, Any]) -> Arm:
        """Build an arm from a bundle's ``metrics.json`` payload."""
        windows = metrics.get("windows")
        if not windows:
            raise ArmSelectionError(f"arm {key!r} carries no per-window metrics")
        return cls(key=key, windows=tuple(windows))


def _window_rows(entry: dict[str, Any]) -> float:
    """How many rows the window contributed, for weighting."""
    for field in ("test_rows_supervised", "test_row_count"):
        value = entry.get(field)
        if value is not None:
            return float(value)
    raise ArmSelectionError(
        "window entry has neither 'test_rows_supervised' nor 'test_row_count'; cannot weight it"
    )


def pooled_metric(entries: Sequence[dict[str, Any]], metric: str = DEFAULT_METRIC) -> float:
    """Row-weighted pool of a per-window metric.

    Exact rather than approximate: run against every window of a real bundle this reproduces
    that run's global metric bit-for-bit, which is what makes walk-forward selection pure
    post-processing. Weighting by window instead of by row would *not* -- windows differ in
    size by an order of magnitude on the busier machines.
    """
    exponent = _POOLING_EXPONENT.get(metric)
    if exponent is None:
        raise ArmSelectionError(
            f"{metric!r} cannot be pooled from per-window values; poolable metrics are "
            f"{sorted(_POOLING_EXPONENT)}"
        )
    total = 0.0
    total_rows = 0.0
    for entry in entries:
        rows = _window_rows(entry)
        try:
            value = float(entry["metrics"][metric])
        except (KeyError, TypeError) as exc:
            raise ArmSelectionError(f"window entry is missing metric {metric!r}") from exc
        total += rows * value**exponent
        total_rows += rows
    if total_rows <= 0:
        raise ArmSelectionError("no scored rows to pool")
    mean = total / total_rows
    # Keep the p=1 case free of a pow() round-trip so MAE stays bit-identical to the bundle.
    return mean if exponent == 1 else mean ** (1.0 / exponent)


def _check_alignment(arms: Sequence[Arm]) -> None:
    """Every arm must be the same rolling split, window for window.

    Arms are separate runs of separate jobs. If one of them was produced from a different
    slice or a different window count, position ``i`` means different things in different
    columns and every comparison below is meaningless -- so this refuses rather than lines
    them up by index and hopes.
    """
    if len(arms) < 2:
        raise ArmSelectionError("walk-forward selection needs at least two arms")
    keys = [arm.key for arm in arms]
    if len(set(keys)) != len(keys):
        raise ArmSelectionError(f"arm keys must be unique, got {keys}")
    if len({len(arm.windows) for arm in arms}) != 1:
        raise ArmSelectionError(
            "arms have different window counts: "
            + ", ".join(f"{arm.key}={len(arm.windows)}" for arm in arms)
        )
    reference = arms[0]
    times = [str(window.get("split_time")) for window in reference.windows]
    for arm in arms[1:]:
        other = [str(window.get("split_time")) for window in arm.windows]
        if other != times:
            i = next(j for j, (a, b) in enumerate(zip(times, other, strict=True)) if a != b)
            raise ArmSelectionError(
                f"arms {reference.key!r} and {arm.key!r} do not share a split at window {i}: "
                f"{times[i]} vs {other[i]}"
            )


def common_scored_indices(arms: Sequence[Arm]) -> tuple[int, ...]:
    """Window positions every arm actually scored.

    A skipped window is a property of the data -- a gap in the job record, typically a
    maintenance outage -- so in practice every arm of a dataset skips the same ones.
    Intersecting anyway keeps the policy's number and the per-arm numbers on one common set;
    otherwise each column of the comparison would be pooling a different set of windows.
    """
    n_windows = len(arms[0].windows)
    return tuple(
        i for i in range(n_windows) if all(arm.windows[i].get("status") == "ok" for arm in arms)
    )


@dataclass(frozen=True)
class WalkForwardResult:
    """What the policy scored, and what it would have scored with hindsight."""

    metric: str
    burn_in: int
    score: float
    scored_windows: int
    scored_rows: int
    choices: tuple[str, ...]
    choice_counts: dict[str, int]
    arm_scores: dict[str, float]
    oracle_key: str
    oracle_score: float
    windows_total: int
    windows_common: int

    @property
    def regret(self) -> float:
        """What choosing without hindsight cost. Never negative, by construction."""
        return self.score - self.oracle_score

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "burn_in": self.burn_in,
            "score": self.score,
            "scored_windows": self.scored_windows,
            "scored_rows": self.scored_rows,
            "choices": list(self.choices),
            "choice_counts": dict(self.choice_counts),
            "arm_scores": dict(self.arm_scores),
            "oracle_key": self.oracle_key,
            "oracle_score": self.oracle_score,
            "regret": self.regret,
            "windows_total": self.windows_total,
            "windows_common": self.windows_common,
        }


def walk_forward(
    arms: Sequence[Arm],
    *,
    metric: str = DEFAULT_METRIC,
    burn_in: int = DEFAULT_BURN_IN,
) -> WalkForwardResult:
    """Choose an arm per window from earlier windows only, and score it on the current one.

    The first ``burn_in`` commonly-scored windows build history and are not scored -- with no
    history there is nothing to choose on, and choosing on one or two windows is choosing on
    noise. Ties go to the earliest arm in ``arms``, so callers control the tie-break by
    ordering (shortest lookback first prefers the cheaper arm when nothing separates them).

    Selection uses all history so far rather than a trailing window. That is the more stable
    estimator; a trailing variant would adapt faster to drift and is worth measuring, but it
    adds a second free parameter to a rule whose purpose is to remove a degree of freedom.
    """
    _check_alignment(arms)
    if burn_in < 1:
        raise ArmSelectionError("burn_in must be at least 1 window")

    common = common_scored_indices(arms)
    if len(common) <= burn_in:
        raise ArmSelectionError(
            f"{len(common)} window(s) were scored by every arm, which is no more than the "
            f"burn-in of {burn_in}: nothing would be left to score"
        )

    by_key = {arm.key: arm for arm in arms}
    choices: list[str] = []
    scored_entries: list[dict[str, Any]] = []
    for position, index in enumerate(common):
        if position < burn_in:
            continue
        history = common[:position]
        history_scores = {
            arm.key: pooled_metric([arm.windows[j] for j in history], metric) for arm in arms
        }
        chosen = min(history_scores, key=history_scores.__getitem__)
        choices.append(chosen)
        scored_entries.append(by_key[chosen].windows[index])

    scored_indices = common[burn_in:]
    arm_scores = {
        arm.key: pooled_metric([arm.windows[j] for j in scored_indices], metric) for arm in arms
    }
    oracle_key = min(arm_scores, key=arm_scores.__getitem__)
    counts = {arm.key: 0 for arm in arms}
    for key in choices:
        counts[key] += 1

    return WalkForwardResult(
        metric=metric,
        burn_in=burn_in,
        score=pooled_metric(scored_entries, metric),
        scored_windows=len(scored_entries),
        scored_rows=int(sum(_window_rows(entry) for entry in scored_entries)),
        choices=tuple(choices),
        choice_counts=counts,
        arm_scores=arm_scores,
        oracle_key=oracle_key,
        oracle_score=arm_scores[oracle_key],
        windows_total=len(arms[0].windows),
        windows_common=len(common),
    )
