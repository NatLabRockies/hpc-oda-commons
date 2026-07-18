"""HPC benchmark-matrix runner: plan the full model x dataset benchmark for a cluster.

This package turns the tracked dataset cards (``docs/benchmarking/datasets/*.card.json``)
plus a *local, gitignored* site config into a set of per-cell Slurm recipes and sbatch
scripts. The site config carries all cluster/user/site-specific values so none of them
leak into the tracked repo; the tracked ``site.example.yml`` and ``templates/*.template``
are placeholders only.
"""

from hpc_oda_commons.benchmarking.hpc.config import (
    DEFAULT_SITE_CONFIG_PATH,
    SiteConfig,
    load_site_config,
)

__all__ = ["DEFAULT_SITE_CONFIG_PATH", "SiteConfig", "load_site_config"]
