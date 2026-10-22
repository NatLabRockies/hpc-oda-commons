"""
Intelligence layer: library-level APIs for programmatic use.

These functions are part of the public API for consumers who import hpc_oda_commons
as a library; no CLI command uses them. docs/reference/python-api.md documents them, and a
test keeps that page listing every name in ``__all__``.
"""

from hpc_oda_commons.intelligence.mapping import (
    suggest_job_runtime_mappings,
    suggest_slurmctld_mappings,
)
from hpc_oda_commons.intelligence.metadata_graph import (
    build_metadata_graph,
    build_metadata_graph_payload,
)
from hpc_oda_commons.intelligence.synthetic_scoring import (
    score_job_runtime_parquet,
    score_job_runtime_rows,
)

__all__ = [
    "suggest_job_runtime_mappings",
    "suggest_slurmctld_mappings",
    "score_job_runtime_parquet",
    "score_job_runtime_rows",
    "build_metadata_graph",
    "build_metadata_graph_payload",
]
