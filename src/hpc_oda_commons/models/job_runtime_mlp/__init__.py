"""Feed-forward MLP model for job runtime prediction with rolling evaluation."""

from hpc_oda_commons.models.job_runtime_mlp.model import (
    JobRuntimeMlpConfig,
    JobRuntimeMlpModel,
)

__all__ = [
    "JobRuntimeMlpConfig",
    "JobRuntimeMlpModel",
]
