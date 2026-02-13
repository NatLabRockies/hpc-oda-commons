from __future__ import annotations

from hpc_oda_commons.qst import cli


def test_validate_state_filter_selection_accepts_exact_values() -> None:
    selected, suggestions = cli._validate_state_filter_selection(
        ["COMPLETED", "FAILED"],
        {"COMPLETED", "FAILED", "RUNNING"},
    )
    assert selected == {"COMPLETED", "FAILED"}
    assert suggestions == {}


def test_validate_state_filter_selection_returns_suggestions_for_invalid_values() -> None:
    selected, suggestions = cli._validate_state_filter_selection(
        ["COMPLETED", "COMPELTED"],
        {"COMPLETED", "FAILED", "RUNNING"},
    )
    assert selected is None
    assert "COMPELTED" in suggestions
    assert "COMPLETED" in suggestions["COMPELTED"]
