# HPC ODA Commons: Comprehensive Technical Reference

## 1. Introduction and Motivation

High-Performance Computing (HPC) sites generate enormous volumes of operational data -- scheduler logs, accounting records, monitoring streams -- but turning that data into actionable insight is needlessly difficult. Each site builds bespoke parsers, schemas, and evaluation pipelines. Results cannot be compared across institutions. Promising analytics ideas remain siloed because there is no shared language for describing the data, the experiments, or the outcomes.

**HPC ODA Commons** (Operational Data Analytics Commons) addresses this by establishing **community-governed contracts** -- versioned schemas, canonical artifacts, and benchmark recipes -- that make ODA workflows **discoverable**, **reproducible**, and **comparable**. It pairs these standards with a practical, CLI-first toolkit that lets operators and researchers go from raw logs to standardized results without sending data off-cluster.

The project is implemented in Python (>=3.10), distributed as the `hpc-oda-commons` package under the Apache-2.0 license, and installed via pip. The CLI entry point is `hpc-oda`. Version 0.1 focuses on **SLURM job runtime prediction** as the inaugural problem domain, with the architecture designed to support additional domains (job failure prediction, resource utilization, queue wait-time modeling) in future versions.

---

## 2. Design Principles

HPC ODA Commons is built on five core principles:

1. **Artifacts are the interface.** Every stage of the pipeline reads and writes stable, versioned artifacts -- Parquet tables, JSON manifests, result bundles. Standards live in the artifact contracts, not in any particular tool's internals. This means any tool that produces conformant artifacts can participate in the ecosystem without depending on HPC ODA Commons code.

2. **Local-first.** Ingestion and analysis run entirely on the user's machine. No data is uploaded or transmitted. Transformation helpers (hashing, binning, redaction) allow users to sanitize artifacts before sharing. This is critical for HPC environments where operational data frequently contains sensitive information (usernames, job scripts, internal hostnames).

3. **Recipe-driven evaluation.** Benchmarks are defined by YAML recipes that fully specify the dataset, model, metrics, and split strategy. "Running the same benchmark" actually means the same thing across sites. This enables rigorous, apples-to-apples comparison of models and methods.

4. **Domain-extensible.** The platform is designed to support multiple ODA problem domains beyond the initial v0.1 focus on job runtime prediction. The schema and registry systems use versioned namespaces that accommodate new problem types without breaking existing contracts.

5. **Reproducibility by construction.** Every result bundle captures full provenance: input file hashes, Python version, package versions, git commit, schema versions. This means any result can be traced back to exactly the data, code, and environment that produced it.

---

## 3. Architecture Overview

### 3.1 End-to-End Data Flow

The HPC ODA Commons pipeline follows a linear progression from raw operational data to comparable, aggregated results:

```
Raw Input (slurmctld.log / site-specific jobs.parquet)
  --> [Adapter/Ingest] parse, profile, map, validate, hash
  --> Canonical ODA Table (Parquet) + Manifest + Quality Report
  --> [Benchmark/Analyze] train model, evaluate metrics via recipe
  --> Result Bundle {result.json, metrics.json, provenance.json}
  --> [Leaderboard] aggregate multiple runs for comparison
```

Each stage produces well-defined, schema-validated artifacts. The canonical ODA table is the pivot point: all upstream work normalizes heterogeneous data into this common format, and all downstream work (modeling, benchmarking, analysis) consumes it.

### 3.2 Package Layout

The codebase is organized into purpose-specific packages under `src/hpc_oda_commons/`:

| Package | Purpose |
|---------|---------|
| `qst/` | **Quickstart Toolkit** -- CLI entry point built on Typer. All user-facing commands live here. |
| `kernel/` | **Core artifact logic** -- ODA tables, manifests, result bundles, mapping specs, provenance, hashing, schema loading, and validation. This is the stable foundation other packages build on. |
| `models/` | **Prediction models** -- Pluggable model implementations. Ships seven models: a deterministic baseline, three rolling-tabular runtime models (XGBoost, Random Forest, MLP), a TF-IDF + kNN runtime model, an embedding + kNN runtime model, and a per-user kNN power model. |
| `models/rolling_tabular/` | **Shared rolling-tabular base** -- `RollingTabularModel` base class plus shared rolling split (`split.py`) and categorical preprocessing (`preprocessing.py`) reused by the XGBoost, Random Forest, and MLP models. |
| `embeddings/` | **Embedding module** -- Serializes job rows to text and encodes them (`hpc-oda embed`), writing an embedded table + provenance manifest for the embedding + kNN model. Model-agnostic; heavy deps are the optional `embed` extra. |
| `ingest/` | **Data adapters** -- Ingestion pipeline for transforming site-specific data into canonical format. Includes profiling, mapping suggestions, interactive wizard, and batch transformation. |
| `adapters/` | **Source parsers** -- Protocol-based adapters for parsing raw data sources. v0.1 includes a slurmctld log parser. |
| `benchmark/` | **Recipe loading and results aggregation** -- Validates benchmark recipes, aggregates result bundles into leaderboards. |
| `schema/` | **Schema validation and quality rules** -- JSON Schema validation, semantic checks, missingness analysis, and quality report generation. |
| `intelligence/` | **Mapping suggestions and metadata** -- Auto-suggestion of field mappings, synthetic data scoring, metadata graph construction. |
| `registry/` | **Offline registry** -- Bundled registry snapshot of known adapters, models, and recipes with filtering and lookup. |
| `integrity/` | **Code integrity** -- Known-good source hashes (`known_hashes.json`) used to verify result bundles against clean commits. |
| `utils/` | **Shared utilities** -- Cross-cutting helpers used by other packages. |
| `tools/` | **Report generation** -- HTML rendering for leaderboards and analysis reports. |
| `datasets/` | **Bundled synthetic datasets** -- Deterministic test datasets for reproducible demos without network access. |
| `schemas/` | **JSON Schema resources** -- Versioned JSON Schema files bundled as package data. |
| `recipes/` | **Benchmark recipe definitions** -- YAML recipe files bundled with the package. |

### 3.3 Artifact Output Paths

The project uses a conventional directory structure for artifacts:

```
<project-root>/
  .hpc_oda/                          # Project state directory
  data/
    ingested/<adapter>/<run_id>/      # Ingested data artifacts
      data.parquet                    #   Canonical ODA table
      manifest.json                  #   Transformation manifest
      data.parquet.quality.json      #   Data quality report
  runs/
    <run_id>/                         # Benchmark result bundles
      result.json                    #   Schema-validated result
      metrics.json                   #   Detailed metrics
      provenance.json                #   Full provenance record
    leaderboard.json                 # Aggregated leaderboard
    index.html                       # Rendered leaderboard
  reports/
    analysis-<id>/                    # Analysis reports
      analysis.json                  #   Analysis data
      index.html                     #   Rendered report
```

---

## 4. Schema Contracts

Schemas are the backbone of the HPC ODA Commons interoperability model. All schemas follow the naming convention `oda.<type>.v<MAJOR>.<MINOR>.<PATCH>` and are stored as JSON Schema (Draft 2020-12) files bundled with the package at `src/hpc_oda_commons/schemas/oda/`. Schema validation is enforced at artifact write time by default.

### 4.1 Job Schema (`oda.job.v0.2.0`)

The canonical job record schema defines the common data model for HPC job data. `oda.job.v0.2.0` is the current version; `oda.job.v0.1.0` is retained for legacy tables only. The schema is intentionally extensible (`additionalProperties: true`) so sites can include extra fields without breaking validation.

**Required fields:**

| Field | Type | Description |
|-------|------|-------------|
| `job_id` | integer or string | Unique job identifier |
| `start_time` | native Arrow `timestamp(us, tz=UTC)` | Job start timestamp. Stored as a native Arrow timestamp column, not an ISO-8601 string; the column type is validated structurally (`collect_job_table_type_issues`), not as a JSON string. |
| `end_time` | native Arrow `timestamp(us, tz=UTC)` | Job end timestamp. Stored as a native Arrow timestamp column, not an ISO-8601 string; validated structurally. |
| `runtime_seconds` | number (or null), minimum 0 | Actual runtime in seconds (`end_time - start_time`) |

**Optional fields defined by the schema:**

| Field | Type | Description |
|-------|------|-------------|
| `submit_time` | native Arrow `timestamp(us, tz=UTC)` | Job submission timestamp. Stored as a native Arrow timestamp column, not an ISO-8601 string; validated structurally. |
| `allocated_cpus` | integer (or null), minimum 1 | CPUs actually allocated |
| `partition` | string (or null) | Queue or partition name |
| `node_list` | string (or null) | Nodes assigned to the job |

Because `additionalProperties: true`, sites may carry any additional columns; only the fields above are defined by the schema itself.

### 4.2 Result Schema (`oda.result.v0.1.0`)

Defines the output format for model evaluation results. A result ties together a recipe, model, dataset, metrics, and provenance into a single validated artifact.

```json
{
  "schema_version": "oda.result.v0.1.0",
  "recipe_id": "recipe.job_runtime.baseline_tiny",
  "problem_domain": ["job-runtime-prediction"],
  "created_at": "2026-01-15T12:00:00Z",
  "metrics": {
    "mae": 123.45,
    "rmse": 234.56
  },
  "provenance": { "..." },
  "model": {
    "id": "model.job_runtime_baseline",
    "version": "0.1.0"
  },
  "dataset": {
    "id": "synthetic/job-runtime/tiny",
    "schema_version": "oda.job.v0.2.0",
    "hash": "sha256_hex_string"
  }
}
```

### 4.3 Manifest Schema (`oda.manifest.v0.1.0`)

Tracks the lineage of data artifacts: what adapter produced the data, what inputs were consumed, what transformations were applied, and the full provenance of the transformation process.

Key sections:
- **adapter**: `{id, version}` identifying the adapter that produced the artifact
- **inputs**: list of input metadata (paths, hashes, sizes, modification times)
- **artifact**: type and path information for the output
- **transformations**: ordered list of transformation operations applied
- **provenance**: environment, code version, and input hash information

### 4.4 Mapping Schema (`oda.mapping.v0.1.0`)

Defines field mapping specifications for transforming site-specific data into the canonical ODA schema. Mapping specs are stored as YAML and support:

- **Source mapping**: direct column-to-field mapping
- **Derived fields**: computed fields (e.g., `runtime_seconds` derived from `end_time - start_time`)
- **Transformations**: typed transformations including timestamp parsing, duration conversion, memory normalization, and identifier hashing
- **Roles**: fields marked as `required` or `optional`

```yaml
schema_version: oda.mapping.v0.1.0
kind: jobs_parquet
output_schema_version: oda.job.v0.2.0
fields:
  job_id:
    source: JobID
    role: required
  start_time:
    source: Start
    role: required
    transform:
      type: timestamp
      format: epoch_s
  runtime_seconds:
    derive: end_time - start_time
    role: required
  user:
    source: User
    role: optional
    transform:
      type: hash_identifier
      salt_env: HPC_ODA_HASH_SALT
```

### 4.5 Recipe Schema (`oda.recipe.v0.1.0`)

Benchmark recipes are the key to reproducible, comparable evaluations. A recipe fully specifies:
- **Dataset**: identifier and path to the canonical Parquet table
- **Model**: identifier and version of the model to evaluate
- **Metrics**: list of metric definitions (must include at minimum MAE and RMSE)
- **Split strategy**: method and parameters for train/test splitting
- **Output**: where to write the result bundle

### 4.6 Metric Definition Language Schema (`oda.mdl.v0.1.0`)

Defines individual metrics to compute from prediction results. Supported metrics: `mae`, `rmse`, `mape`, `r2`, `underprediction_ratio`. Each metric specifies a `name`, `target` field, and optional `params`.

### 4.7 Registry Schema (`oda.registry.v0.1.0`)

The registry schema defines the structure for cataloguing adapters, models, and recipes. Each entry includes metadata (name, version, description, problem domain, supported sources, schema versions) and a reference (either a Python module path or a repository-relative file path).

---

## 5. Command-Line Interface

The CLI is built on Typer and exposed as the `hpc-oda` command. It provides a complete workflow from project initialization through data ingestion, validation, benchmarking, analysis, and result aggregation.

### 5.1 Root Commands

| Command | Description |
|---------|-------------|
| `hpc-oda init` | Initialize a local HPC ODA Commons project. Creates `.hpc_oda/`, `data/`, and `runs/` directories. |
| `hpc-oda run-baseline` | Run an offline baseline demo using the bundled tiny synthetic dataset. Produces a result bundle without any external data or network access. |
| `hpc-oda benchmark <recipe>` | Run a benchmark defined by a YAML recipe file. Resolves the model, loads the dataset, executes the evaluation strategy, computes metrics, and writes a validated result bundle. |
| `hpc-oda analyze --data <path>` | Analyze a local dataset with the baseline model and emit a report bundle (JSON + HTML). |
| `hpc-oda validate <path>` | Validate artifacts against their schemas. Accepts result bundles, manifests, or Parquet files. |
| `hpc-oda embed <parquet> --out <path>` | Serialize job rows to text and encode them into a dense `embedding` column (for `model.job_runtime_embedding_knn`). Writes an embedded Parquet + provenance manifest. `--model stub` needs no download; real models need the `embed` extra. |
| `hpc-oda leaderboard --runs <dir> --out <dir>` | Aggregate result bundles from a runs directory into a leaderboard (JSON + HTML). Includes Validated and Code Hash columns. |
| `hpc-oda record-hash` | Record the current source code hash and git commit in `integrity/known_hashes.json`. Run after tests pass on a clean commit. |
| `hpc-oda browse` | Browse the registry snapshot. Supports filters: `--tag`, `--type`, `--source`, `--input-schema`, `--output-schema`. |
| `hpc-oda info <entry_id>` | Display detailed metadata for a registry entry (adapter, model, or recipe). |

### 5.2 Ingest Subcommands

| Command | Description |
|---------|-------------|
| `hpc-oda ingest slurmctld --path <path>` | Parse a slurmctld log file into a canonical ODA job Parquet table with manifest and quality report. |
| `hpc-oda ingest jobs-parquet --path <path>` | Ingest a site-specific jobs Parquet file. Supports `--mapping <path>` for a pre-built mapping spec, `--non-interactive` mode, `--hash-identifiers / --no-hash-identifiers`, `--sample-rows N`, and `--batch-size N`. |

### 5.3 Typical Workflows

**Offline demo (no data required):**
```bash
hpc-oda init
hpc-oda run-baseline
```

**Ingest from slurmctld logs:**
```bash
hpc-oda init
hpc-oda ingest slurmctld --path /var/log/slurmctld.log
hpc-oda validate data/ingested/slurmctld/*/data.parquet
```

**Full benchmark cycle:**
```bash
hpc-oda init
hpc-oda ingest jobs-parquet --path site_jobs.parquet
hpc-oda benchmark src/hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

---

## 6. Ingestion Pipeline

The ingestion pipeline transforms heterogeneous site-specific data into the canonical ODA schema. It is designed to handle the diversity of data formats across HPC sites while providing a guided, interactive experience for first-time users and a non-interactive, reproducible path for automated workflows.

### 6.1 Source Adapters

Adapters implement the `SourceAdapter` protocol, which requires a `metadata` property (providing adapter ID, version, supported sources, and schema versions) and a `parse(path: Path) -> list[dict]` method.

**slurmctld Adapter** (`adapter.slurmctld`):
- Parses SLURM controller log files using regex pattern matching
- Extracts job allocation events (`Allocate JobId=X NodeList=... #CPUs=Y Partition=...`) and completion events (`_job_complete: JobId=X done`)
- Correlates allocation and completion events by job ID to compute runtime
- Outputs canonical records with `job_id`, `start_time`, `end_time`, `runtime_seconds`, and optional `allocated_cpus`, `partition`, `node_list`
- Skips incomplete jobs (missing either allocation or completion)

### 6.2 Jobs Parquet Ingestion

For sites that already have job data in Parquet format but with non-canonical column names and types, the `jobs-parquet` ingestion pipeline provides a four-stage process:

**Stage 1: Profiling** (`ingest/jobs_parquet/profile.py`)
- Samples up to 200 rows from the input Parquet file
- For each column, computes a `ColumnProfile` with: normalized name, Arrow data type, inferred kind (timestamp, numeric, categorical, unknown), null rate, and sample values
- Normalization converts column names to lowercase with underscores and alphanumeric characters only

**Stage 2: Suggestion** (`ingest/jobs_parquet/suggest.py`)
- Maintains an alias table for 19 canonical fields (e.g., `job_id` matches aliases like `jobid`, `slurm_job_id`, `slurmjobid`)
- Scoring: exact alias match = 1.0 confidence, substring match = 0.7, kind compatibility = +0.3/-0.2 adjustment
- Returns ranked candidates per canonical field with confidence scores and reasons

**Stage 3: Interactive Wizard** (`ingest/jobs_parquet/wizard.py`)
- Walks the user through mapping each canonical field to a source column
- For each mapped field, prompts for unit/format information:
  - Timestamps: iso8601, epoch_s, epoch_ms, epoch_us
  - Durations: seconds, minutes, hours, HH:MM:SS
  - Memory: bytes, KB, MB, GB, KiB, MiB, GiB
- Offers optional identifier hashing with configurable salt environment variable
- Produces a mapping spec YAML file

**Stage 4: Apply** (`ingest/jobs_parquet/apply.py`)
- Reads the input Parquet in configurable batch sizes (default 50,000 rows)
- Applies transformations column-at-a-time (vectorized over whole Arrow columns rather than literally per row), then derives computed fields
- Supported transformations: `timestamp` (format parsing to a native Arrow `timestamp(us, tz=UTC)` column, not an ISO-8601 string), `duration` (unit conversion to seconds), `memory` (unit conversion to MB), `memory_slurm` (parses a SLURM memory string such as `160G`, `2366M`, or a bare `4096` into MiB), `hash_identifier` (SHA-256 with optional salt)
- Derived fields: `runtime_seconds` can be computed from `end_time - start_time`
- Optional state filtering (e.g., keep only COMPLETED jobs)
- Skips rows missing required fields
- Returns summary with row counts (total, kept, skipped, state-filtered)

### 6.3 Ingestion Output

Each ingestion run produces a directory under `data/ingested/<adapter>/<run_id>/` containing:
- `data.parquet` -- canonical ODA table validated against `oda.job.v0.2.0`
- `manifest.json` -- transformation lineage validated against `oda.manifest.v0.1.0`
- `data.parquet.quality.json` -- data quality assessment

---

## 7. Prediction Models

HPC ODA Commons ships seven models: six for job runtime prediction (baseline, XGBoost, Random Forest, MLP, TF-IDF + kNN, Embedding + kNN) and one for job power prediction (per-user kNN). The runtime models operate on `rows`, a list of dictionaries conforming to the job schema, with `runtime_seconds` as the target field. The XGBoost, Random Forest, and MLP models are rolling-tabular models that share a common base class (`RollingTabularModel`); the shared rolling split (`split.py`) and categorical preprocessing now live in `models/rolling_tabular/`, so they are no longer XGBoost-only.

### 7.1 Baseline Model (`model.job_runtime_baseline`)

A deterministic mean predictor that serves as the lower bound for model comparison:

- **Fit**: computes the arithmetic mean of `runtime_seconds` across all training rows
- **Predict**: returns that constant mean value for every input row
- **Purpose**: establishes a floor for more sophisticated models. Any useful model should outperform the baseline.

The baseline model has no dependencies beyond the Python standard library and serves as a fast, reliable reference point.

### 7.2 XGBoost Model (`model.job_runtime_xgboost`)

A gradient-boosted tree model with automatic categorical preprocessing and a rolling evaluation strategy that simulates production retraining. This is the primary model for demonstrating the HPC ODA Commons benchmarking workflow.

#### 7.2.1 Configuration

The model is controlled by `JobRuntimeXGBoostConfig`, a frozen dataclass with the following key parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_windows` | 1000 | Number of recent windows to evaluate |
| `training_lookback_days` | 100 | Days of historical data for each training window |
| `explained_variance_target` | 0.95 | Target explained variance for SVD dimensionality reduction |
| `infrequent_category_fraction` | 0.001 | Fraction threshold for rare category collapsing |
| `min_frequency_floor` | 2 | Minimum absolute count for a category to remain uncollapsed |
| `target_max_one_hot_width` | 2048 | Maximum total one-hot encoded feature width before SVD |
| `max_svd_components` | 256 | Maximum SVD components to retain |
| `n_estimators` | 100 | XGBoost trees |
| `max_depth` | 8 | Maximum tree depth |
| `learning_rate` | 0.05 | Boosting learning rate |
| `random_state` | 42 | Random seed for reproducibility |

#### 7.2.2 Feature Engineering Pipeline

The XGBoost model implements an automated feature engineering pipeline that handles the heterogeneous, high-cardinality categorical features common in HPC job data:

1. **Categorical Detection**: Scans all columns and identifies those with string or boolean values as categorical. Excludes the target field and timestamp fields.

2. **Categorical Profiling**: For each categorical column, computes cardinality, null rate, frequency distribution, and identifies infrequent categories.

3. **One-Hot Encoding Configuration**: Adaptively selects a `min_frequency` threshold that keeps the total one-hot encoded width below `target_max_one_hot_width` (default 2048). Uses scikit-learn's `OneHotEncoder` with `handle_unknown="infrequent_if_exist"` to gracefully handle unseen categories at test time. The `min_frequency` threshold is explicitly tied to the daily training set size used when one-hot and SVD are fit, ensuring the threshold scales appropriately with data volume.

4. **Dimensionality Reduction**: Applies Truncated SVD to the one-hot encoded matrix, selecting the number of components needed to achieve the `explained_variance_target` (default 95%). This compresses high-dimensional sparse categorical features into a dense, lower-dimensional representation.

5. **Numeric Features**: Numeric columns are passed through directly with null values filled as 0.0.

6. **Feature Concatenation**: The final feature matrix is formed by horizontally stacking the numeric features and the SVD-reduced categorical features.

#### 7.2.3 Rolling Evaluation

The rolling evaluation strategy (`evaluate()`) simulates how a model would perform if retrained and deployed on a recurring schedule. This is more realistic than a single train/test split because it captures temporal dynamics in HPC workloads.

**Split construction** (`models/rolling_tabular/split.py`, shared with the Random Forest and MLP models):
- The evaluation window covers the `n_windows` most recent periods in the dataset
- For each split at time `t`:
  - **Train window**: all jobs where `end_time` falls in `[t - lookback_days, t)`
  - **Test window**: all jobs where `submit_time` falls in `[t, t + test_window_hours)`
- This enforces strict temporal separation: the model is trained only on jobs that completed before the split point, and tested only on jobs submitted after the split point
- Each split records a `day_key` (the date of the split time) to support daily preprocessing caching

**Daily preprocessing cache** (`DailyPreprocessingCache`):
- One-hot encoding and SVD are computationally expensive, especially with high-cardinality features
- To avoid redundant computation, the preprocessing pipeline (encoder fitting, SVD fitting) is cached by `day_key`
- The first split of each day triggers a full preprocessing refit; subsequent splits within the same day reuse the cached encoder and SVD transformer
- This provides a realistic simulation of production behavior (daily preprocessing refresh) while remaining computationally tractable

**Evaluation loop**:
- For each split:
  1. Materialize train and test rows from index lists
  2. Filter rows with valid, finite `runtime_seconds` targets
  3. Retrieve or create daily preprocessing artifacts (encoder + SVD)
  4. Transform train and test rows into feature matrices
  5. Fit a fresh XGBoost regressor on training features
  6. Generate predictions on test features
  7. Compute per-window MAE and RMSE
  8. Skip splits with insufficient data (< 2 training rows, 0 test rows, or no features after preprocessing)
- After all splits: compute global (aggregate) MAE and RMSE across all scored predictions

**Output**: The model returns a structured dictionary containing:
- Global metrics (MAE, RMSE aggregated across all scored windows)
- Per-window entries with status, metrics, feature info, preprocessing details
- Summary statistics (windows scored/skipped, preprocessing refits, total rows scored)

### 7.3 TF-IDF + kNN Model (`model.job_runtime_tfidf_knn`)

A text-similarity model that predicts runtime by finding the most similar historical jobs based on their metadata text. This model is most effective when data includes rich text fields like job names, submit commands, working directories, and job scripts.

#### 7.3.1 Configuration

Controlled by `JobRuntimeTfidfKnnConfig`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `n_windows` | 1000 | Number of rolling evaluation windows |
| `test_window_hours` | 6 | Hours per test window |
| `training_lookback_days` | 100 | Training lookback |
| `k` | 5 | Number of nearest neighbors |
| `n_hash_features` | 16384 | HashingVectorizer feature count |
| `ngram_range` | (1, 1) | N-gram range for text vectorization |
| `use_incremental_cache` | True | Reuse hash matrix across windows |
| `log_target` | False | Predict in log-space |

#### 7.3.2 How It Works

1. **Text column auto-detection**: Scans for string-valued columns, excluding timestamps, target, and job_id.
2. **Text concatenation**: Joins all text column values per job into a single space-separated string.
3. **HashingVectorizer + TF-IDF**: Hashes text into a fixed-width sparse feature matrix, then applies TF-IDF weighting.
4. **k-nearest neighbors**: Finds the k most similar training jobs by cosine distance.
5. **Weighted prediction**: Predicts runtime as the similarity-weighted average of the neighbors' runtimes.

#### 7.3.3 Incremental Cache

The model maintains an incremental hash matrix cache across rolling windows. Between windows, only new/removed jobs are hashed -- the rest of the matrix is reused. This avoids re-vectorizing the full training set each window and provides significant speedup for rolling evaluation.

### 7.4 Random Forest Model (`model.job_runtime_random_forest`)

An alternate runtime prediction model using scikit-learn's Random Forest regression. It subclasses the neutral `RollingTabularModel` base and reuses the shared rolling split and automatic categorical one-hot/SVD preprocessing (from `models/rolling_tabular/`), differing from the XGBoost model only in the underlying regressor. Like XGBoost, it uses the rolling evaluation strategy with a daily preprocessing cache.

### 7.5 MLP Model (`model.job_runtime_mlp`)

An alternate runtime prediction model using a feed-forward neural network (scikit-learn's `MLPRegressor`). It also subclasses `RollingTabularModel` and reuses the shared rolling split and categorical one-hot/SVD preprocessing, swapping in the MLP regressor. It is driven by the bundled `mlp_rolling.yml` recipe.

### 7.6 Embedding + kNN Model (`model.job_runtime_embedding_knn`)

The embedding-space counterpart to the TF-IDF + kNN model. Instead of vectorizing text internally, it consumes a **precomputed dense `embedding` column** (produced by `hpc-oda embed`) and predicts runtime as the similarity-weighted average of the *k* nearest neighbors in embedding space, under the same rolling-window evaluation. Search is an exact dense top-k with a selectable backend (`numpy` default, optional `torch`/`faiss`). Because it reuses the shared rolling split (`models/rolling_tabular/split.py`) and `kernel.metrics`, it is directly comparable to the other runtime models. Driven by the bundled `embedding_knn_rolling.yml` recipe. See [Embedding-based kNN](how-to/embedding-knn.md).

### 7.7 Job Power Model (`model.job_power_uopc`)

A per-user kNN power-prediction model (UoPC-style) that predicts `maxpcon` (maximum job power) rather than runtime. Unlike the rolling runtime models, it uses a fixed train/test split. For each user, job history is ordered by end time and the most recent `theta` jobs form the training context; categorical job features (e.g., job name) are label-encoded per fit, and a `KNeighborsRegressor` predicts from the nearest neighbors. It operates on raw Fugaku-style columns (`usr`, `jnam`, `cnumr`, `nnumr`, `edt`, `maxpcon`) via field aliases, and is driven by the bundled `uopc_maxpcon.yml` recipe.

---

## 8. Benchmarking System

The benchmarking system connects datasets, models, metrics, and split strategies through YAML recipe definitions. It is designed so that the same recipe run at different sites produces results that can be meaningfully compared.

### 8.1 Recipe Structure

A recipe is a YAML file validated against `oda.recipe.v0.1.0`. It specifies:

```yaml
recipe_id: recipe.job_runtime.xgb_hourly_recent
problem_domain: [job-runtime-prediction]
schema_version: oda.job.v0.2.0
dataset:
  id: site-jobs-2026
  table_path: data/ingested/jobs_parquet/run-001/data.parquet
model:
  id: model.job_runtime_xgboost
  version: "0.1.0"
metrics:
  - name: mae
    target: runtime_seconds
  - name: rmse
    target: runtime_seconds
split:
  method: rolling
  n_windows: 1000
  test_window_hours: 6
  training_lookback_days: 100
run:
  output_dir: runs
  overwrite: false
```

**Validation rules:**
- Metrics must be a list with at minimum `mae` and `rmse`
- All metrics must target the same field
- For `rolling` splits: `n_windows` must be positive; `test_window_hours` defaults to 6; `training_lookback_days` defaults to 100
- For `fixed` splits: `train_fraction` and `seed` control the random split

### 8.2 Bundled Recipes

The package ships five recipes:

| Recipe | Model | Split | Purpose |
|--------|-------|-------|---------|
| `baseline_tiny.yml` | Baseline | Fixed 80/20 | CI smoke tests, offline demos |
| `xgb_hourly_recent.yml` | XGBoost | Rolling (1000 windows, 6h, 100d) | Full XGBoost benchmark |
| `alt_model_example.yml` | XGBoost | Rolling (24 windows, 6h, 30d) | Alternate configuration example |
| `mlp_rolling.yml` | MLP | Rolling (20 windows, 6h, 7d) | Feed-forward MLP runtime benchmark |
| `uopc_maxpcon.yml` | Job Power (UoPC) | Fixed 80/20 | Per-user kNN power (`maxpcon`) prediction |

### 8.3 Result Bundles

Each benchmark run produces a result bundle directory containing three JSON files:

**`result.json`** -- The primary result artifact, validated against `oda.result.v0.1.0`. Contains the recipe ID, problem domain, metrics summary, model metadata, dataset metadata (including content hash), and provenance.

**`metrics.json`** -- Detailed metrics. For rolling evaluations, this includes per-window entries with individual metrics, feature information, and skip reasons, as well as the summary statistics.

**`provenance.json`** -- Complete reproducibility record:
- Schema versions used (input and result)
- Python version
- Package versions (optionally via pip freeze)
- Package version and git commit hash
- Input file metadata (path, SHA-256 hash, size, modification time)

### 8.4 Leaderboard

The leaderboard system aggregates multiple result bundles into a sorted comparison:

1. Scans a runs directory for subdirectories containing `result.json`
2. Validates each bundle
3. Extracts key fields: creation time, recipe ID, model, dataset, metrics
4. Sorts entries by creation time
5. Writes `leaderboard.json` and renders `index.html` with a tabular view

---

## 9. Provenance and Reproducibility

Provenance tracking is woven throughout HPC ODA Commons. The `build_provenance()` function in `kernel/provenance.py` captures:

```python
{
    "schema_versions": {
        "input": "oda.job.v0.2.0",
        "result": "oda.result.v0.1.0"
    },
    "environment": {
        "python": "3.12.1",
        "packages": ["hpc-oda-commons==0.1.0", ...]
    },
    "code": {
        "package_version": "0.1.0",
        "git_commit": "abc123...",
        "source_hash": "def456..."
    },
    "inputs": [
        {
            "path": "data/ingested/.../data.parquet",
            "sha256": "e3b0c44...",
            "size_bytes": 1048576,
            "mtime_epoch": 1706140800.0
        }
    ]
}
```

**Content hashing**: Parquet tables are content-hashed using SHA-256 over the raw file bytes (read in 1 MB chunks). This hash is stored in the result bundle's `dataset.hash` field, enabling verification that the exact same data was used across different benchmark runs.

**Input hashing**: The `HashedInput` dataclass captures path, SHA-256 hash, file size, and modification time for each input file. This enables detection of whether inputs have changed between runs.

**Code integrity verification**: Result bundles include an `integrity` block with `code_hash` (SHA-256 of all `.py` files in the package), `validated` (true if the hash matches a known-good commit in `integrity/known_hashes.json`), and `git_commit`. This detects both accidental and intentional code modifications that could bias results. Run `hpc-oda record-hash` after tests pass on a clean commit to register it.

**Data transformation utilities** in `kernel/transformations.py` support privacy-preserving workflows:
- `hash_identifier(value, salt)`: SHA-256 hashes sensitive identifiers (e.g., usernames) with an optional salt

---

## 10. Registry System

The registry provides a discoverable catalogue of known adapters, models, and recipes. In v0.1, the registry is distributed as a bundled JSON snapshot packaged with the `hpc-oda-commons` installation.

### 10.1 Registry Entries

Each registry entry is a `RegistryEntry` dataclass with:
- **id**: unique identifier (e.g., `adapter.slurmctld`, `model.job_runtime_xgboost`)
- **entry_type**: `adapter`, `model`, or `recipe`
- **name, version, description**: human-readable metadata
- **problem_domain**: tuple of supported domains (e.g., `("job-runtime-prediction",)`)
- **supported_sources**: tuple of data sources the entry works with
- **input_schema_version / output_schema_version**: schema compatibility
- **reference**: either a Python module path (`kind="python"`, `module`, `object`) or a repo-relative file path (`kind="path"`, `path`)
- **tags, license, dependencies**: additional metadata

### 10.2 v0.1 Registry Contents

The bundled registry snapshot contains 37 entries: one adapter, seven models, four recipes, and 25 datasets (registered via the `oda.registry.v0.2.0` `dataset` entry_type). A representative subset:

| ID | Type | Description |
|----|------|-------------|
| `adapter.slurmctld` | adapter | Parses slurmctld log files into canonical job records |
| `model.job_runtime_baseline` | model | Deterministic mean-prediction baseline |
| `model.job_runtime_xgboost` | model | XGBoost with rolling evaluation |
| `model.job_runtime_tfidf_knn` | model | TF-IDF + kNN with rolling evaluation |
| `model.job_runtime_random_forest` | model | Random Forest with rolling evaluation |
| `model.job_runtime_mlp` | model | Feed-forward MLP with rolling evaluation |
| `model.job_power_uopc` | model | Per-user kNN power prediction (UoPC-style, fixed split) |
| `recipe.job_runtime.baseline_tiny` | recipe | Tiny synthetic dataset benchmark |
| `recipe.job_runtime.xgb_hourly_recent` | recipe | XGBoost rolling benchmark |

### 10.3 Registry Index and Filtering

The `RegistryIndex` provides in-memory lookup and filtering:
- `get(entry_id)`: direct lookup by ID
- `filter(tag, entry_type, source, input_schema, output_schema)`: multi-criteria filtering

The CLI commands `browse` and `info` expose these capabilities to users.

### 10.4 Metadata Graph

The intelligence layer can construct a metadata graph from the registry snapshot, with nodes representing entries, tags, domains, sources, and schemas, and edges representing relationships (has_tag, has_domain, supports_source, input_schema, output_schema). This graph enables visualization and exploration of the ecosystem's structure.

---

## 11. Data Quality and Validation

### 11.1 Schema Validation

All artifacts are validated against their JSON Schemas using the Draft 2020-12 validator from the `jsonschema` library. Validation occurs:
- At write time for manifests, result bundles, and mapping specs (can be disabled with `validate=False`)
- On demand via the `hpc-oda validate` command
- During ingestion as part of the quality report

### 11.2 Semantic Validation

Beyond schema conformance, the validator performs semantic checks specific to the problem domain:
- **Negative runtime**: flags rows where `runtime_seconds < 0`
- **Timestamp ordering**: flags rows where `start_time > end_time`
- **Timestamp validity**: flags rows with unparseable timestamp values

**Structural timestamp-type check**: JSON Schema cannot express Arrow column types, so `collect_job_table_type_issues()` structurally verifies that the `start_time`, `end_time`, and `submit_time` columns are native Arrow `timestamp(us, tz=UTC)`. The microsecond unit and UTC timezone are pinned, so accidental drift (seconds/nanoseconds, or an untyped column) is caught -- this also rejects legacy `oda.job.v0.1.0` tables that stored timestamps as ISO-8601 strings.

### 11.3 Quality Report

The `validate_parquet_with_quality()` function in `schema/validator.py` produces a comprehensive quality report:

- **Schema errors**: grouped by error type with example rows (up to 3 per error type)
- **Semantic errors**: grouped by issue type with examples
- **Missingness**: per-field null rate (0.0 to 1.0)
- **Timestamp issues**: count of rows with timestamp problems
- **Negative runtime**: count of rows with negative runtime values

In strict mode (the default), any schema or semantic errors raise a `SchemaValidationError`.

### 11.4 Synthetic Scoring

The intelligence layer provides a `score_job_runtime_rows()` function that assesses data quality along multiple dimensions:
- **Coverage score**: 1.0 minus the average missing rate across required fields
- **Runtime positive rate**: fraction of runtime values that are positive
- **Runtime mean**: average runtime in seconds
- **Partition diversity**: count of unique partition values
- **CPU range**: min/max allocated CPU counts

---

## 12. Dependencies and Technology Stack

### 12.1 Core Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| typer | >= 0.12.0 | CLI framework with type annotations |
| rich | >= 13.7.0 | Rich terminal output (tables, progress, formatting) |
| tqdm | >= 4.66.0 | Progress bars for long-running operations |
| PyYAML | >= 6.0.1 | YAML parsing for recipes and mapping specs |
| pyarrow | >= 14.0.0 | Parquet I/O and columnar data handling |
| jsonschema | >= 4.0.0 | JSON Schema validation (Draft 2020-12) |
| scikit-learn | >= 1.3.0 | OneHotEncoder, TruncatedSVD |
| xgboost | >= 2.0.0 | Gradient-boosted tree model |

### 12.2 Development Dependencies

pytest, ruff (linting and formatting), mypy (type checking), and pre-commit hooks. Line length is 100 characters. The project targets Python 3.10+.

### 12.3 Conda Environment

A `cpu.yml` recipe is provided for creating a Conda environment with Python 3.11 and the necessary dependencies.

---

## 13. Testing Strategy

### 13.1 Test Organization

Tests are organized into two tiers:

- **Unit tests** (`tests/unit/`): ~42 test files covering individual components. Run with `make test` or `pytest -q`. No external dependencies required.

- **Integration tests** (`tests/integration/`): End-to-end CLI workflow tests. Require `HPC_ODA_OFFLINE=1`. Run with `make test-integration`. Optional native XGBoost tests gated behind `HPC_ODA_ENABLE_NATIVE_XGBOOST_IT=1`.

### 13.2 Integration Test Coverage

The golden path integration test (`test_cli_golden_path.py`) validates the complete workflow:

1. `init` -- project structure creation
2. `ingest slurmctld` -- log parsing to canonical Parquet
3. `validate` -- schema and quality validation
4. `benchmark` -- recipe-driven model evaluation
5. `analyze` -- report generation
6. `leaderboard` -- result aggregation

Each integration test runs in an isolated temporary directory to prevent cross-test contamination.

### 13.3 Test Fixtures

- **Slurmctld log fixture**: a minimal 3-job log file with deterministic timestamps
- **Recipe fixture**: a baseline_tiny recipe pointing to the bundled synthetic dataset
- **Synthetic dataset**: a deterministic 30-row Parquet file bundled at `datasets/synthetic/job-runtime/tiny/data.parquet`

---

## 14. Extensibility and Future Directions

HPC ODA Commons v0.1 establishes the foundational contracts and tooling. The architecture is explicitly designed for extension along several axes:

### 14.1 New Problem Domains

The `problem_domain` field in results, recipes, and registry entries is a list, allowing entries to span or target new domains. Planned domains include:
- **Job failure prediction**: predicting whether a job will fail before completion
- **Resource utilization analysis**: modeling CPU, memory, and GPU efficiency
- **Queue wait-time prediction**: estimating time-to-start for submitted jobs

Each new domain would add a corresponding job schema extension (while maintaining backwards compatibility via `additionalProperties: true`), new model implementations, and new benchmark recipes.

### 14.2 New Source Adapters

The `SourceAdapter` protocol is intentionally minimal. Adding support for a new data source (e.g., PBS/Torque logs, Slurm accounting via `sacct`, cloud HPC schedulers) requires only implementing the `parse()` method and providing `AdapterMetadata`.

### 14.3 New Models

The model interface (fit/predict with list-of-dict rows) is deliberately simple. Future models could include:
- Neural network models (LSTMs for temporal patterns)
- Ensemble methods combining multiple base models
- Transfer learning approaches for cross-site generalization

### 14.4 Community Registry

The current offline registry snapshot is a stepping stone toward a community-governed registry where sites can publish and discover adapters, models, and recipes. The registry schema already supports version, license, and reference metadata needed for this.

### 14.5 Visualization

The `viz` optional dependency group is reserved for future visualization capabilities using Streamlit or Dash, enabling interactive exploration of benchmark results, data quality reports, and leaderboards.

### 14.6 Cross-Site Comparison

The ultimate vision is enabling rigorous cross-site comparison of ODA methods. With standardized schemas, reproducible recipes, and comprehensive provenance, researchers can:
- Run the same benchmark recipe against their local data
- Share result bundles (not raw data) with full provenance
- Aggregate results into cross-site leaderboards
- Identify models and methods that generalize across HPC environments

---

## 15. Development Configuration

- **Linting/Formatting**: Ruff with line length 100, Python 3.10 target, rules E/F/I/UP/B
- **Pre-commit hooks**: trailing whitespace, end-of-file fixer, YAML/TOML/JSON validation, 512 KB file size limit, Ruff
- **Editor config**: LF line endings, UTF-8, 2-space indentation

---

## Appendix A: Schema Version Index

| Schema ID | Purpose |
|-----------|---------|
| `oda.job.v0.2.0` | Canonical HPC job record (current) |
| `oda.job.v0.1.0` | Canonical HPC job record (legacy; retained for older tables only) |
| `oda.result.v0.1.0` | Benchmark result output |
| `oda.manifest.v0.1.0` | Data artifact lineage |
| `oda.mapping.v0.1.0` | Field mapping specification |
| `oda.recipe.v0.1.0` | Benchmark recipe definition |
| `oda.mdl.v0.1.0` | Metric Definition Language |
| `oda.registry.v0.1.0` | Registry entry catalogue |

Note: `oda.leaderboard.v0.1.0` is not a bundled JSON Schema. It is a version tag emitted in leaderboard output, defined by the `LEADERBOARD_FORMAT_VERSION` constant in `benchmark/results.py`.

## Appendix B: CLI Command Quick Reference

```text
hpc-oda init
hpc-oda run-baseline
hpc-oda ingest slurmctld --path <log-file>
hpc-oda ingest jobs-parquet --path <parquet-file> [--mapping <yaml>] [--non-interactive]
hpc-oda validate <artifact-path>
hpc-oda embed <parquet-file> --out <embedded.parquet> [--model <stub|hf-id>] [--config <local.yml>]
hpc-oda benchmark <recipe.yml>
hpc-oda analyze --data <parquet-file>
hpc-oda leaderboard --runs <dir> --out <dir>
hpc-oda datasets fetch <dataset-id> | prepare <dataset-id>
hpc-oda browse [--tag X] [--type adapter|model|recipe|dataset] [--source X]
hpc-oda info <entry_id>
```

## Appendix C: Environment Variables

| Variable | Purpose |
|----------|---------|
| `HPC_ODA_OFFLINE` | Run in offline mode (required for integration tests) |
| `HPC_ODA_CLI` | Override CLI executable path |
| `HPC_ODA_HASH_SALT` | Salt for identifier hashing |
| `HPC_ODA_ENABLE_NATIVE_XGBOOST_IT` | Enable native XGBoost integration tests |
