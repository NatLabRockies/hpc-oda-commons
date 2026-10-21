"""A recipe's metric target is the column the model predicts, never just a label (#204).

Metrics are computed from whatever the model predicted, so before this a recipe could
score runtime predictions under a power column's name and nothing would notice.
"""

from __future__ import annotations

import pytest

from hpc_oda_commons.benchmark import runner


def _metrics(target: str) -> list[dict[str, str]]:
    return [{"name": "mae", "target": target}, {"name": "rmse", "target": target}]


def test_recipe_target_is_the_shared_metric_target() -> None:
    assert runner.recipe_target(_metrics("avgpcon_per_node")) == "avgpcon_per_node"
    assert runner.recipe_target([{"name": "mae"}]) is None


def test_recipe_target_rejects_metrics_that_disagree() -> None:
    with pytest.raises(ValueError, match="share one target"):
        runner.recipe_target(
            [{"name": "mae", "target": "runtime_seconds"}, {"name": "rmse", "target": "maxpcon"}]
        )


def test_a_runtime_model_cannot_be_scored_as_power() -> None:
    """The silent case: a model that predicts runtime, a recipe that says power."""

    class RuntimeOnlyModel:
        target_field = "runtime_seconds"

        def evaluate(self, rows, **_):  # pragma: no cover - must not be reached
            raise AssertionError("evaluate must not run for a mismatched target")

    with pytest.raises(ValueError, match="predicts 'runtime_seconds'.*'avgpcon_per_node'"):
        runner._run_rolling_model_evaluate(
            RuntimeOnlyModel(),
            [{"dummy": 1}],
            split={"method": "rolling", "n_windows": 1},
            metric_defs=_metrics("avgpcon_per_node"),
            verbose=False,
            capture_artifacts=False,
        )


def test_the_fixed_uopc_adaptation_only_scores_maxpcon() -> None:
    with pytest.raises(ValueError, match="'maxpcon'"):
        runner.run_fixed_uopc(
            [{"dummy": 1}],
            split={"method": "fixed", "train_fraction": 0.8, "seed": 42},
            metric_defs=_metrics("avgpcon"),
        )


def test_the_cutoff_protocol_rejects_a_target_it_does_not_predict() -> None:
    with pytest.raises(ValueError, match="'avgpcon_per_node' or 'maxpcon_per_node'"):
        runner.run_cutoff_uopc(
            [{"dummy": 1}],
            split={"method": "cutoff", "test_start": "2024-02-01"},
            metric_defs=_metrics("runtime_seconds"),
        )


def test_the_cutoff_headline_follows_the_recipe_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Peak power can be the headline: the recipe's target picks it, not a hard-coded key."""

    class FakeUopcModel:
        def evaluate_paper_reproduction(self, rows, **_):
            return {
                "avgpcon_per_node": {"mae": 1.0, "rmse": 2.0},
                "maxpcon_per_node": {"mae": 3.0, "rmse": 4.0},
                "summary": {},
            }

    monkeypatch.setattr(runner, "UopcModel", FakeUopcModel)

    metrics, payload, _ = runner.run_cutoff_uopc(
        [{"dummy": 1}],
        split={"method": "cutoff", "test_start": "2024-02-01"},
        metric_defs=_metrics("maxpcon_per_node"),
    )

    assert metrics == {"mae": 3.0, "rmse": 4.0}
    assert payload["run_config"]["headline_target"] == "maxpcon_per_node"
