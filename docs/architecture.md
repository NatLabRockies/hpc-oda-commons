# Architecture

Internal architecture reference for developers (and developer agents). For the
contribution process and coding standards, see
[`CONTRIBUTING.md`](../CONTRIBUTING.md). For using the tool, see
[`agent-usage.md`](agent-usage.md).

## Data flow

```
Raw Input (slurmctld.log / jobs.parquet)
  -> [Adapter/Ingest] parse, profile, map, validate, hash
  -> Canonical ODA Table (Parquet) + Manifest + Quality Report
  -> [Benchmark/Analyze] train model, evaluate metrics via recipe
  -> Result Bundle {result.json, metrics.json, provenance.json}
  -> [Leaderboard] aggregate multiple runs
```

## Package layout (`src/hpc_oda_commons/`)

- **`qst/`** -- CLI entry point (Typer). Entry point: `hpc-oda = hpc_oda_commons.qst.cli:app`.
  Orchestrates only; business logic belongs in kernel/models/benchmark.
- **`kernel/`** -- Core primitives: ODA tables, manifests, mapping specs, result bundles,
  provenance, hashing, metrics (`metrics.py`), serialization (`serialization.py`).
- **`models/`** -- Prediction models:
  - `job_runtime_baseline/` -- deterministic mean-prediction model (fit/predict)
  - `rolling_tabular/` -- neutral base package for the rolling tabular runtime models:
    `RollingTabularModel` + `RollingTabularConfig` (`base.py`), categorical preprocessing
    (OHE + SVD via `preprocessing.py`), and the daily preprocessing cache / split logic
    (`split.py`). Concrete models supply a regressor via the `_new_regressor()` seam.
    (This is the "neutral base" refactor from issue #6, now landed.)
  - `job_runtime_xgboost/` -- XGBoost regressor; subclasses `RollingTabularModel` and supplies
    an XGBoost regressor via `_new_regressor()`.
  - `job_runtime_random_forest/`, `job_runtime_mlp/` -- Random Forest and MLP regressors that
    also subclass `RollingTabularModel`, reusing the shared `rolling_tabular` preprocessing and
    splits and overriding only the regressor.
  - `job_runtime_tfidf_knn/` -- TF-IDF + kNN with rolling evaluation (`evaluate()`),
    HashingVectorizer with incremental cache (`vectorization.py`)
  - `job_power_uopc/` -- user-based online power prediction (UoPC), fixed chronological split,
    per-user kNN (`evaluate_fixed()`)
- **`benchmark/`** -- Recipe loading (`recipes.py`), results aggregation (`results.py`),
  benchmark execution (`runner.py`), optional run artifacts (`run_extras.py`), and shared
  leaderboard formatting (`leaderboard_display.py`).
- **`ingest/`** -- Ingestion pipeline: `jobs_parquet/` (profile, suggest, wizard, apply).
- **`adapters/`** -- Source parsers: `slurmctld/` (regex-based log parser). Protocol:
  `SourceAdapter` in `base.py`.
- **`schema/`** -- JSON Schema validation (`validator.py`) and semantic quality rules
  (`quality_rules.py`).
- **`intelligence/`** -- Library-level APIs (not CLI-integrated): mapping suggestions,
  metadata graph, synthetic scoring.
- **`registry/`** -- Offline registry snapshot with filtering and lookup.
- **`tools/`** -- Report generation: `report/html.py` (HTML), `report/console.py` (Rich console).
- **`datasets/`** -- Bundled synthetic datasets for offline demos.
- **`schemas/`** -- JSON Schema files (Draft 2020-12), versioned as `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>`.
- **`recipes/`** -- Bundled benchmark recipe YAMLs. This is the only location for bundled
  recipes; custom/trial recipes go in a gitignored `recipes/` at the repo root.

## Testing conventions

- **Unit tests** (`tests/unit/`): fast, no external dependencies. Run with `make test`.
- **Integration tests** (`tests/integration/`): end-to-end CLI workflows. Require
  `HPC_ODA_OFFLINE=1`. Run with `make test-integration`. Optional:
  `HPC_ODA_ENABLE_NATIVE_XGBOOST_IT=1` for native XGBoost integration tests.
- **Test fixtures**: generate in temp dirs (`tmp_path`); never rely on gitignored files or
  machine-specific absolute paths. Keep fixtures deterministic and minimal.
- **Monkeypatching models**: integration tests that exercise the XGBoost / TF-IDF kNN / MLP /
  UoPC benchmark paths monkeypatch the model on `runner.` (e.g. `runner.JobRuntimeXGBoostModel`),
  not via `cli.` -- the models are imported in `benchmark/runner.py`.
- **Cross-environment numeric reproducibility** is a known limitation for fitted-model metric
  values; see [`known-issues.md`](known-issues.md) (issue #2).

## Documentation map

- `README.md` -- project overview, quickstart, design principles.
- `docs/agent-usage.md` -- using the tool (CLI workflow).
- `docs/how-to/`, `docs/reference/`, `docs/concepts/` -- guides and reference.
- `docs/hpc-oda-commons-reference.md` -- comprehensive single-document reference.
- `CONTRIBUTING.md` -- contribution process, quality gates, coding standards.

If CLI commands, flags, or output paths change, update `README.md`,
`docs/how-to/quickstart.md`, `docs/reference/cli.md`, and `docs/agent-usage.md`.
