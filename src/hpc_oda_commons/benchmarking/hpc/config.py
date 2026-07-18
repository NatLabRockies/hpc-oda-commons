"""Load and validate the *local* HPC site config for the benchmark-matrix runner.

The site config is a small YAML file holding every cluster/user/site-specific value the
runner needs (ssh alias, account, partitions, paths, env). It is **not** tracked — the
default location is ``.hpc_oda/hpc-site.yml`` (gitignored). The tracked
``site.example.yml`` next to this module is a placeholder template to copy from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SITE_SCHEMA_VERSION = "oda.hpc_site.v0.1.0"
DEFAULT_SITE_CONFIG_PATH = Path(".hpc_oda/hpc-site.yml")

# Keys that must be present and non-empty in the site config.
_REQUIRED_KEYS = ("host", "user", "account", "remote_base", "env_prefix", "partitions")
_REQUIRED_PARTITIONS = ("cpu", "bigmem", "gpu")


class SiteConfigError(ValueError):
    """Raised when the local site config is missing, malformed, or incomplete."""


@dataclass(frozen=True)
class SiteConfig:
    """Resolved cluster/site settings for one benchmark run.

    All fields come from the local (gitignored) site YAML. Nothing here is tracked, so
    site-specific values never enter the repo.
    """

    host: str
    user: str
    account: str
    remote_base: str
    env_prefix: str
    partitions: dict[str, str]
    gpu_gres: str = "gpu:1"
    conda_module: str = ""
    gpu_host: str = ""
    embedding_model: str = "microsoft/harrier-oss-v1-0.6b"
    source_path: Path | None = field(default=None, compare=False)

    # --- derived remote paths (everything lives under remote_base) ---
    @property
    def repo_dir(self) -> str:
        """Working directory on the cluster: the git clone the benchmark runs from."""
        return f"{self.remote_base}/hpc-oda-commons"

    @property
    def hpc_oda(self) -> str:
        """Absolute path to the ``hpc-oda`` CLI inside the cluster conda env."""
        return f"{self.env_prefix}/bin/hpc-oda"

    @property
    def python(self) -> str:
        return f"{self.env_prefix}/bin/python"

    @property
    def cache_dir(self) -> str:
        """Vector cache dir for embed resume (``embed --cache-dir``)."""
        return f"{self.remote_base}/cache"

    @property
    def hf_home(self) -> str:
        """Shared Hugging Face home (``HF_HOME``). The embedding model is pre-staged into
        ``{hf_home}/hub`` so embed jobs load it offline (compute nodes have no internet)."""
        return f"{self.remote_base}/hf"

    def partition(self, kind: str) -> str:
        try:
            return self.partitions[kind]
        except KeyError as exc:  # pragma: no cover - guarded by validation
            raise SiteConfigError(f"no partition configured for {kind!r}") from exc


def load_site_config(path: Path | None = None) -> SiteConfig:
    """Load the local site config, or raise a clear error pointing to the example.

    Parameters
    ----------
    path:
        Explicit config path. Defaults to ``.hpc_oda/hpc-site.yml`` under the CWD.
    """
    cfg_path = Path(path) if path is not None else DEFAULT_SITE_CONFIG_PATH
    if not cfg_path.exists():
        example = Path(__file__).with_name("site.example.yml")
        raise SiteConfigError(
            f"HPC site config not found at {cfg_path}. Copy the example and fill in your "
            f"cluster's values (keep it gitignored):\n"
            f"  cp {example} {cfg_path}\n"
            f"then edit {cfg_path}. It must NOT be committed (site-specific values stay local)."
        )

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SiteConfigError(f"{cfg_path}: expected a YAML mapping, got {type(raw).__name__}.")

    return _build(raw, cfg_path)


def _build(raw: dict[str, Any], cfg_path: Path) -> SiteConfig:
    missing = [k for k in _REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise SiteConfigError(f"{cfg_path}: missing required keys: {', '.join(missing)}.")

    version = str(raw.get("schema_version", ""))
    if version and version != SITE_SCHEMA_VERSION:
        raise SiteConfigError(
            f"{cfg_path}: unsupported schema_version {version!r} "
            f"(this runner expects {SITE_SCHEMA_VERSION})."
        )

    partitions = raw.get("partitions")
    if not isinstance(partitions, dict):
        raise SiteConfigError(f"{cfg_path}: 'partitions' must be a mapping.")
    part_missing = [k for k in _REQUIRED_PARTITIONS if not partitions.get(k)]
    if part_missing:
        raise SiteConfigError(
            f"{cfg_path}: partitions missing: {', '.join(part_missing)} "
            f"(need {', '.join(_REQUIRED_PARTITIONS)})."
        )

    # Reject obvious placeholder values so a half-filled example can't be run by accident.
    placeholders = {
        k: v
        for k, v in raw.items()
        if isinstance(v, str) and (v.startswith("your-") or v.startswith("/path/to/"))
    }
    if placeholders:
        raise SiteConfigError(
            f"{cfg_path}: still contains example placeholders "
            f"({', '.join(sorted(placeholders))}); fill in your real values."
        )

    return SiteConfig(
        host=str(raw["host"]),
        user=str(raw["user"]),
        account=str(raw["account"]),
        remote_base=str(raw["remote_base"]).rstrip("/"),
        env_prefix=str(raw["env_prefix"]).rstrip("/"),
        partitions={k: str(partitions[k]) for k in _REQUIRED_PARTITIONS},
        gpu_gres=str(raw.get("gpu_gres", "gpu:1")),
        conda_module=str(raw.get("conda_module", "")),
        gpu_host=str(raw.get("gpu_host", "")),
        embedding_model=str(raw.get("embedding_model", "microsoft/harrier-oss-v1-0.6b")),
        source_path=cfg_path,
    )
