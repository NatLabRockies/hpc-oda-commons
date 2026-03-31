# Install

## Editable install (dev)
```bash
pip install -e ".[dev]"
```

## Minimal install
```bash
pip install -e .
```

Optional extras are listed in `pyproject.toml` under `project.optional-dependencies`.

## Offline install options (recommended for HPC)

When you need to install without outbound network access, use one of the approaches below.

### Option A: Local wheelhouse (recommended)

1. On a machine with network access, build a wheelhouse:
   ```bash
   python -m pip download -d wheelhouse "hpc-oda-commons[dev]" --no-binary :none:
   python -m pip wheel -w wheelhouse .
   ```
2. Copy `wheelhouse/` to the target system.
3. Install from the local wheelhouse:
   ```bash
   pip install --no-index --find-links wheelhouse hpc-oda-commons
   ```

### Option B: Internal package index or mirror

Point `pip` at your internal index and install normally:
```bash
pip install hpc-oda-commons
```

### Notes on build isolation

Some environments prevent network access during build. If you are installing from
source in a locked-down environment, use:

```bash
pip install -e . --no-build-isolation
```

This requires build dependencies (e.g., `setuptools`, `wheel`) to already be available.
