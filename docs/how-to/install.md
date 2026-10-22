# Install

hpc-oda-commons needs Python 3.10 or later. Install it from a clone of the repository.

## Editable install (dev)
```bash
pip install -e ".[dev]"
```

## Minimal install
```bash
pip install -e .
```

Optional extras are listed in `pyproject.toml` under `project.optional-dependencies`.
Notable extras: `dev` (test/lint toolchain), `embed` (real embedding models for `hpc-oda
embed`), and `torch` / `faiss` (accelerated dense-search backends for the embedding-kNN
model). Install with, e.g., `pip install -e ".[embed]"`.

Keep `embed` in an environment of its own: on macOS, torch and XGBoost crash in one process
([known issues](../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).
Compute embeddings there, and run benchmarks and tests in an environment without it.

## Offline install options (recommended for HPC)

When you need to install without outbound network access, use one of the approaches below.

### Option A: Local wheelhouse (recommended)

1. On a machine with network access, from the clone, build wheels for the package and
   everything it needs:
   ```bash
   python -m pip wheel -w wheelhouse ".[dev]"
   ```
2. Copy `wheelhouse/` to the target system.
3. Install from the local wheelhouse:
   ```bash
   pip install --no-index --find-links wheelhouse "hpc-oda-commons[dev]"
   ```

### Option B: Internal package index or mirror

If your site publishes the package (or its wheelhouse) to an internal index, point `pip` at
it and install normally:
```bash
pip install "hpc-oda-commons[dev]"
```

### Notes on build isolation

Some environments prevent network access during build. If you are installing from
source in a locked-down environment, use:

```bash
pip install -e . --no-build-isolation
```

This requires build dependencies (e.g., `setuptools`, `wheel`) to already be available.
