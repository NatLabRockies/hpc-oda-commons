"""The ids models had before #249, and the ids they have now.

The models were first named for the task they began on (``model.job_runtime_xgboost``),
though each one predicts whatever target its recipe names. Result bundles and recipes
written before #249 keep those ids, so anything that reads a bundle or a recipe maps them
here. The table is fixed: the old ids will never change.
"""

from __future__ import annotations

LEGACY_MODEL_IDS: dict[str, str] = {
    "model.job_runtime_baseline": "model.baseline",
    "model.job_runtime_xgboost": "model.xgboost",
    "model.job_runtime_moe_xgboost": "model.moe_xgboost",
    "model.job_runtime_tfidf_knn": "model.tfidf_knn",
    "model.job_runtime_embedding_knn": "model.embedding_knn",
    "model.job_runtime_signature_memorizer": "model.signature_memorizer",
    "model.job_runtime_random_forest": "model.random_forest",
    "model.job_runtime_mlp": "model.mlp",
    "model.job_power_uopc": "model.uopc",
}


def canonical_model_id(model_id: str) -> str:
    """A model's current id: an id from before #249 maps to its new one, any other is kept."""
    return LEGACY_MODEL_IDS.get(model_id, model_id)
