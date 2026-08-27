"""Unit tests for walk-forward lookback-arm selection (#190)."""

from __future__ import annotations

import math

import pytest

from hpc_oda_commons.benchmark.arm_selection import (
    Arm,
    ArmSelectionError,
    common_scored_indices,
    compact_arm_label,
    derive_arm_keys,
    pooled_metric,
    walk_forward,
)


def _window(
    index: int,
    mae: float,
    *,
    rows: int = 10,
    status: str = "ok",
    rmse: float | None = None,
) -> dict:
    return {
        "split_time": f"2026-01-{index + 1:02d}T00:00:00+00:00",
        "status": status,
        "test_rows_supervised": rows,
        "metrics": {"mae": mae, "rmse": mae if rmse is None else rmse},
    }


def _arm(key: str, maes: list[float], **kwargs) -> Arm:
    return Arm(key=key, windows=tuple(_window(i, m, **kwargs) for i, m in enumerate(maes)))


# --- pooling is row-weighted, and exact ------------------------------------------------


def test_pooled_mae_weights_by_rows_not_by_window() -> None:
    """Window sizes differ by an order of magnitude on busy machines, so this is not cosmetic.

    One tiny window with a large error and one large window with none: the row-weighted
    answer is 1.0, a flat mean over windows would say 5.0.
    """
    entries = [_window(0, 10.0, rows=1), _window(1, 0.0, rows=9)]
    assert pooled_metric(entries, "mae") == 1.0


def test_pooled_rmse_pools_quadratically() -> None:
    """RMSE is the p=2 power mean; pooling it linearly would understate it."""
    entries = [_window(0, 0.0, rows=1, rmse=0.0), _window(1, 0.0, rows=1, rmse=10.0)]
    assert pooled_metric(entries, "rmse") == pytest.approx(math.sqrt(50.0))
    assert pooled_metric(entries, "rmse") != pytest.approx(5.0)


def test_pooled_mae_is_bit_exact_for_a_single_window() -> None:
    """The p=1 path must not round-trip through pow(), or it stops matching the bundle."""
    value = 15297.47365627263
    assert pooled_metric([_window(0, value, rows=1633)], "mae") == value


@pytest.mark.parametrize("metric", ["r2", "mape"])
def test_metrics_that_do_not_pool_are_refused(metric: str) -> None:
    """r2 is normalised per window and mape has its own denominator: both would be wrong."""
    with pytest.raises(ArmSelectionError, match="cannot be pooled"):
        pooled_metric([_window(0, 1.0)], metric)


def test_window_without_a_row_count_is_refused() -> None:
    entry = {"split_time": "t", "status": "ok", "metrics": {"mae": 1.0}}
    with pytest.raises(ArmSelectionError, match="test_rows_supervised"):
        pooled_metric([entry], "mae")


# --- arms must describe the same split -------------------------------------------------


def test_arms_of_different_lengths_are_refused() -> None:
    with pytest.raises(ArmSelectionError, match="different window counts"):
        walk_forward([_arm("10d", [1.0, 2.0]), _arm("120d", [1.0])], burn_in=1)


def test_arms_on_different_splits_are_refused() -> None:
    """Lining mismatched runs up by index would compare different weeks silently."""
    a = _arm("10d", [1.0, 2.0, 3.0])
    shifted = Arm(key="120d", windows=tuple(_window(i + 5, 1.0) for i in range(3)))
    with pytest.raises(ArmSelectionError, match="do not share a split at window 0"):
        walk_forward([a, shifted], burn_in=1)


def test_duplicate_arm_keys_are_refused() -> None:
    with pytest.raises(ArmSelectionError, match="unique"):
        walk_forward([_arm("10d", [1.0, 2.0]), _arm("10d", [1.0, 2.0])], burn_in=1)


def test_a_single_arm_is_refused() -> None:
    with pytest.raises(ArmSelectionError, match="at least two arms"):
        walk_forward([_arm("10d", [1.0, 2.0])], burn_in=1)


def test_arm_from_metrics_requires_windows() -> None:
    with pytest.raises(ArmSelectionError, match="no per-window metrics"):
        Arm.from_metrics("10d", {"mae": 1.0, "windows": []})


# --- skipped windows -------------------------------------------------------------------


def test_common_scored_indices_drops_a_window_any_arm_skipped() -> None:
    """Scoring the arms on different window sets would make the comparison table a fiction."""
    a = _arm("10d", [1.0, 2.0, 3.0])
    b = Arm(
        key="120d",
        windows=(_window(0, 1.0), _window(1, 0.0, status="skipped"), _window(2, 3.0)),
    )
    assert common_scored_indices([a, b]) == (0, 2)


# --- the policy ------------------------------------------------------------------------

# Arm "short" wins the first two windows and loses the rest; "long" is the reverse. With a
# burn-in of 2 the policy must stay on "short" for one window past the crossover -- that lag
# is the honest cost of choosing without hindsight, and a leak would erase it.
_SHORT = [1.0, 1.0, 9.0, 9.0, 9.0, 9.0]
_LONG = [6.0, 6.0, 1.0, 1.0, 1.0, 1.0]


def _crossover_arms() -> list[Arm]:
    return [_arm("short", _SHORT), _arm("long", _LONG)]


def test_policy_scores_the_arm_chosen_from_earlier_windows_only() -> None:
    result = walk_forward(_crossover_arms(), burn_in=2)
    # Windows 2 and 3 are scored on "short" (chosen from history that still favours it),
    # windows 4 and 5 on "long" once the running average has crossed over: (9+9+1+1)/4.
    assert result.choices == ("short", "short", "long", "long")
    assert result.score == pytest.approx(5.0)
    assert result.scored_windows == 4
    assert result.scored_rows == 40


def test_policy_does_not_peek_at_the_window_it_is_scored_on() -> None:
    """The regression guard: including the current window flips window 3 and scores 3.0."""
    result = walk_forward(_crossover_arms(), burn_in=2)
    assert result.score != pytest.approx(3.0)


def test_oracle_is_the_best_single_arm_on_the_same_windows() -> None:
    result = walk_forward(_crossover_arms(), burn_in=2)
    assert result.arm_scores == pytest.approx({"short": 9.0, "long": 1.0})
    assert result.oracle_key == "long"
    assert result.oracle_score == pytest.approx(1.0)
    # The gap is the selection bias the naive rule would have hidden.
    assert result.regret == pytest.approx(4.0)


def test_regret_is_never_negative() -> None:
    """Hindsight cannot lose to the policy, so a negative regret means the rule leaked."""
    result = walk_forward(_crossover_arms(), burn_in=2)
    assert result.regret >= 0.0


def test_choice_counts_cover_every_arm_including_unchosen_ones() -> None:
    result = walk_forward([_arm("short", _SHORT), _arm("long", _LONG)], burn_in=5)
    assert result.choice_counts == {"short": 0, "long": 1}


def test_ties_go_to_the_first_arm_given() -> None:
    """Deterministic tie-break, so callers order shortest-lookback-first to prefer it."""
    flat_a = _arm("short", [1.0, 1.0, 5.0])
    flat_b = _arm("long", [1.0, 1.0, 5.0])
    assert walk_forward([flat_a, flat_b], burn_in=2).choices == ("short",)
    assert walk_forward([flat_b, flat_a], burn_in=2).choices == ("long",)


def test_burn_in_must_leave_something_to_score() -> None:
    with pytest.raises(ArmSelectionError, match="nothing would be left to score"):
        walk_forward(_crossover_arms(), burn_in=6)


def test_burn_in_of_zero_is_refused() -> None:
    """With no history there is nothing to choose on."""
    with pytest.raises(ArmSelectionError, match="at least 1 window"):
        walk_forward(_crossover_arms(), burn_in=0)


def test_result_serialises_to_json_ready_types() -> None:
    result = walk_forward(_crossover_arms(), burn_in=2).to_dict()
    assert result["choices"] == ["short", "short", "long", "long"]
    assert result["windows_total"] == 6
    assert result["windows_common"] == 6
    assert result["regret"] == pytest.approx(4.0)


# --- arm keys derived from the recorded configuration (#197) ---------------------------


def test_arm_keys_name_whatever_differs() -> None:
    keys = derive_arm_keys(
        [
            {"training_lookback_days": 10, "objective": "reg:absoluteerror"},
            {"training_lookback_days": 120, "objective": "reg:absoluteerror"},
        ]
    )
    assert keys == ("training_lookback_days=10", "training_lookback_days=120")


def test_arm_keys_work_for_an_axis_the_code_has_never_heard_of() -> None:
    """The point of #197: a new knob must not require teaching this function about it."""
    keys = derive_arm_keys(
        [{"target_encode_min_cardinality": 0}, {"target_encode_min_cardinality": 500}]
    )
    assert keys == ("target_encode_min_cardinality=0", "target_encode_min_cardinality=500")


def test_arm_keys_combine_several_differing_knobs() -> None:
    keys = derive_arm_keys(
        [
            {"training_lookback_days": 10, "target_encode_min_cardinality": 0},
            {"training_lookback_days": 30, "target_encode_min_cardinality": 500},
        ]
    )
    assert keys[0] == "target_encode_min_cardinality=0+training_lookback_days=10"


def test_identically_configured_bundles_are_refused() -> None:
    """Two runs of one configuration are a cell measured twice, not two arms."""
    with pytest.raises(ArmSelectionError, match="configured identically"):
        derive_arm_keys([{"training_lookback_days": 30}, {"training_lookback_days": 30}])


def test_execution_only_knobs_do_not_make_an_axis() -> None:
    """window_n_jobs shifts the last decimals via summation order; that is not an arm."""
    with pytest.raises(ArmSelectionError, match="configured identically"):
        derive_arm_keys(
            [
                {"training_lookback_days": 30, "window_n_jobs": 1},
                {"training_lookback_days": 30, "window_n_jobs": 24},
            ]
        )


def test_int_and_float_spellings_are_the_same_arm() -> None:
    """30 and 30.0 must not split one arm into two."""
    with pytest.raises(ArmSelectionError, match="configured identically"):
        derive_arm_keys([{"training_lookback_days": 30}, {"training_lookback_days": 30.0}])


def test_a_knob_present_in_only_one_config_still_distinguishes() -> None:
    keys = derive_arm_keys([{"a": 1}, {"a": 1, "time_decay_rate": 0.05}])
    assert keys == ("time_decay_rate=None", "time_decay_rate=0.05")


def test_compact_label_drops_the_axis_name_for_a_single_axis() -> None:
    assert compact_arm_label("training_lookback_days=120") == "120"
    assert compact_arm_label("a=1+b=2") == "a=1+b=2"
