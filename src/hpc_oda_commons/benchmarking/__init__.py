"""Benchmarking support: dataset characterization, health-gating, and window selection.

This package produces the reproducible **dataset cards** that drive the runtime-prediction
benchmark. A card records each dataset's characterization (span, job rate, temporal-gap
health, feature cardinality, runtime distribution) and the chosen 3-month rolling-benchmark
window (with rationale), so the choices are explainable and repeatable for others.

See ``docs/benchmarking/methodology.md`` for the agreed methodology.
"""

from hpc_oda_commons.benchmarking.cards import build_card, render_card_markdown, write_card
from hpc_oda_commons.benchmarking.characterize import (
    CARD_SCHEMA_VERSION,
    CharacterizeError,
    characterize_table,
    select_window,
)

__all__ = [
    "CARD_SCHEMA_VERSION",
    "CharacterizeError",
    "characterize_table",
    "select_window",
    "build_card",
    "render_card_markdown",
    "write_card",
]
