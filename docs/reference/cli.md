# CLI reference

Every `hpc-oda` command and option, generated from the CLI's own `--help` text. Don't edit
this page: change the help text in `src/hpc_oda_commons/qst/` and run `make docs-cli`.

Run the commands from the root of a checkout. Several defaults are paths in the repository,
such as `docs/benchmarking/datasets` and `docs/models`.

For the workflows these commands make up, see the [quickstart](../how-to/quickstart.md) and
[Benchmark your own data](../how-to/benchmark-your-data.md).

## Environment variables

| Variable | Effect |
|---|---|
| `HPC_ODA_OFFLINE` | `1` makes `datasets fetch` and `datasets prepare` refuse the network. The integration tests set it. |
| `HPC_ODA_CACHE_DIR` | Where fetched datasets are cached. Default `.hpc_oda/cache/datasets`. |
| `HPC_ODA_PREPROCESSING_CACHE` | Where the rolling tabular models keep their preprocessing between runs. Default `.hpc_oda/cache/preprocessing`; `off` turns it off. |
| `HPC_ODA_HASH_SALT` | The salt for hashed identifiers, when a mapping names it in `salt_env` (the ingest wizard does). |

## Commands

Benchmark HPC job runtime and power prediction, on public data or your own.

**Usage**:

```console
$ hpc-oda [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `browse`: List the registry's models, datasets,...
* `info`: Show one registry entry's metadata.
* `embed`: Embed an ingested job table into an...
* `init`: Initialize a local hpc-oda-commons project...
* `run-baseline`: Run an offline baseline demo using a...
* `benchmark`: Run a benchmark recipe: one model, one...
* `analyze`: Analyze a local dataset with the baseline...
* `validate`: Validate an artifact against its schema.
* `leaderboard`: Generate leaderboard.json, index.html and...
* `record-hash`: Record the current source code hash for...
* `ingest`: Ingest operational data into canonical ODA...
* `datasets`: Fetch, prepare, characterize, slice and...
* `bench-matrix`: Plan the full model x dataset benchmark...
* `models`: Commands about the registered models.
* `recipes`: Write the benchmark's recipes for a...

### `hpc-oda browse`

List the registry's models, datasets, recipes and adapters.

**Usage**:

```console
$ hpc-oda browse [OPTIONS]
```

**Options**:

* `--tag TEXT`: Filter by tag or problem domain.
* `--type TEXT`: Filter by entry type (adapter, model, recipe, dataset).
* `--source TEXT`: Filter by supported source.
* `--input-schema TEXT`: Filter by input schema version.
* `--output-schema TEXT`: Filter by output schema version.
* `--snapshot PATH`: Read this registry snapshot JSON instead of the package's registry.
* `--help`: Show this message and exit.

### `hpc-oda info`

Show one registry entry's metadata.

**Usage**:

```console
$ hpc-oda info [OPTIONS] ENTRY_ID
```

**Arguments**:

* `ENTRY_ID`: Registry entry ID (e.g., model.baseline).  [required]

**Options**:

* `--snapshot PATH`: Read this registry snapshot JSON instead of the package's registry.
* `--help`: Show this message and exit.

### `hpc-oda embed`

Embed an ingested job table into an embedded parquet + provenance manifest.

**Usage**:

```console
$ hpc-oda embed [OPTIONS] INPUT_PATH
```

**Arguments**:

* `INPUT_PATH`: Ingested job parquet  [required]

**Options**:

* `--out PATH`: Output embedded parquet path  [required]
* `--model TEXT`: 'stub' or a sentence-transformers model id  [default: stub]
* `--format TEXT`: prose | kv  [default: prose]
* `--config PATH`: Local YAML (extra_text_columns, instruction, ...)
* `--device TEXT`: auto, cpu, cuda or mps (auto picks the best found)  [default: auto]
* `--dtype TEXT`: fp16, fp32 or bf16  [default: fp16]
* `--batch-size INTEGER`: Rows the model encodes at a time  [default: 32]
* `--chunk-size INTEGER`: Rows per cache chunk  [default: 1000]
* `--cache-dir PATH`: Vector cache dir (enables resume)
* `--instruction TEXT`: Prefix each row with this model instruction
* `--trust-remote-code`: Let the model run its own code from its repository
* `--help`: Show this message and exit.

### `hpc-oda init`

Initialize a local hpc-oda-commons project in the current directory.

**Usage**:

```console
$ hpc-oda init [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `hpc-oda run-baseline`

Run an offline baseline demo using a deterministic tiny synthetic dataset.
Writes a result bundle under ./runs/.

**Usage**:

```console
$ hpc-oda run-baseline [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `hpc-oda benchmark`

Run a benchmark recipe: one model, one dataset, one split.

Writes a result bundle under the recipe's run.output_dir (default runs/).

**Usage**:

```console
$ hpc-oda benchmark [OPTIONS] RECIPE
```

**Arguments**:

* `RECIPE`: The recipe YAML to run.  [required]

**Options**:

* `-v, --verbose`: Print progress updates during benchmark execution.
* `--help`: Show this message and exit.

### `hpc-oda analyze`

Analyze a local dataset with the baseline model and emit a report bundle.

**Usage**:

```console
$ hpc-oda analyze [OPTIONS]
```

**Options**:

* `--data PATH`: A job Parquet file, or an ingest run folder holding data.parquet.  [required]
* `--out PATH`: Folder the report bundle goes under.  [default: reports]
* `--help`: Show this message and exit.

### `hpc-oda validate`

Validate an artifact against its schema.

- A result bundle folder: checks result.json.
- A manifest.json: checks it against the manifest schema.
- A Parquet file: checks its first rows as oda.job.v0.2.0.

**Usage**:

```console
$ hpc-oda validate [OPTIONS] PATH
```

**Arguments**:

* `PATH`: A result bundle, manifest.json or Parquet file.  [required]

**Options**:

* `--help`: Show this message and exit.

### `hpc-oda leaderboard`

Generate leaderboard.json, index.html and runs.html from the result bundles in --runs.

index.html has one leaderboard per target: a row per model, its average headroom, and a
column per dataset. runs.html lists every bundle and why any was not counted.

**Usage**:

```console
$ hpc-oda leaderboard [OPTIONS]
```

**Options**:

* `--runs PATH`: Runs directory containing result bundles.  [default: runs]
* `--out PATH`: Output directory for leaderboard.  [default: leaderboard]
* `--ceilings PATH`: Folder of error ceilings and runtime cards, for headroom and the roster.  [default: docs/benchmarking/datasets]
* `--recipes PATH`: A folder of power recipes from `hpc-oda recipes write`, whose runs count (repeatable).
* `--help`: Show this message and exit.

### `hpc-oda record-hash`

Record the current source code hash for this git commit.

Appends a (git_commit, source_hash) entry to the package's
src/hpc_oda_commons/integrity/known_hashes.json.
Run this after tests pass on a clean commit to register it as validated.

**Usage**:

```console
$ hpc-oda record-hash [OPTIONS]
```

**Options**:

* `--help`: Show this message and exit.

### `hpc-oda ingest`

Ingest operational data into canonical ODA artifacts.

**Usage**:

```console
$ hpc-oda ingest [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `slurmctld`: Ingest slurmctld log into canonical...
* `jobs-parquet`: Ingest a jobs Parquet export into...

### `hpc-oda ingest slurmctld`

Ingest slurmctld log into canonical oda.job.v0.2.0 Parquet + manifest.

**Usage**:

```console
$ hpc-oda ingest slurmctld [OPTIONS]
```

**Options**:

* `--path PATH`: The slurmctld log to read.  [required]
* `--help`: Show this message and exit.

### `hpc-oda ingest jobs-parquet`

Ingest a jobs Parquet export into canonical oda.job.v0.2.0 artifacts.

Writes data/ingested/jobs_parquet/<run>/: data.parquet, its quality report, a manifest and,
from the wizard, mapping.yml.

**Usage**:

```console
$ hpc-oda ingest jobs-parquet [OPTIONS]
```

**Options**:

* `--path PATH`: The Parquet export to read.  [required]
* `--mapping PATH`: A mapping.yml from an earlier run. Without it, a wizard builds one.
* `--sample-rows INTEGER`: Rows the wizard profiles to suggest a mapping.  [default: 200]
* `--batch-size INTEGER`: Rows converted at a time.  [default: 50000]
* `--non-interactive`: Never prompt: requires --mapping, and skips the job-state filter question.
* `--hash-identifiers / --no-hash-identifiers`: The wizard's default for hashing user and account. No effect with --mapping.  [default: hash-identifiers]
* `--help`: Show this message and exit.

### `hpc-oda datasets`

Fetch, prepare, characterize, slice and card datasets, and compute their ceilings.

**Usage**:

```console
$ hpc-oda datasets [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `fetch`: Fetch a dataset's files...
* `prepare`: Fetch, decode, and normalize a dataset...
* `characterize`: Check a prepared table's health, choose...
* `cards`: Write a card for every dataset, generated...
* `ceiling`: Compute the minimum error any submit-time...
* `slice`: Cut a prepared table to a window you name,...

### `hpc-oda datasets fetch`

Fetch a dataset's files (checksum-verified) into the local cache.

**Usage**:

```console
$ hpc-oda datasets fetch [OPTIONS] DESCRIPTOR
```

**Arguments**:

* `DESCRIPTOR`: Path to a dataset descriptor YAML.  [required]

**Options**:

* `--slice TEXT`: Named slice to fetch (default: the descriptor's default).
* `--all`: Fetch every resource, ignoring slices (may be large).
* `--max-size TEXT`: Refuse downloads at/above this size (e.g. 5GB, 500MB).  [default: 5GB]
* `--cache PATH`: Cache root (default: .hpc_oda/cache/datasets or HPC_ODA_CACHE_DIR).
* `--from PATH`: For gated/manual datasets: a local dir holding the file(s).
* `--offline / --no-offline`: Refuse network (default: on if HPC_ODA_OFFLINE=1).
* `-y, --yes`: Proceed even when the download size is unknown.
* `--help`: Show this message and exit.

### `hpc-oda datasets prepare`

Fetch, decode, and normalize a dataset into canonical ODA table(s).

**Usage**:

```console
$ hpc-oda datasets prepare [OPTIONS] DESCRIPTOR
```

**Arguments**:

* `DESCRIPTOR`: Path to a dataset descriptor YAML.  [required]

**Options**:

* `--slice TEXT`: Named slice (default: the descriptor's default).
* `--all`: Use every resource, ignoring slices (may be large).
* `--target TEXT`: Only prepare the target with this output schema.
* `--max-size TEXT`: Refuse downloads at/above this size.  [default: 5GB]
* `--cache PATH`: Cache root (default: .hpc_oda/cache/datasets or HPC_ODA_CACHE_DIR).
* `--out PATH`: Output root for canonical tables (default: current directory).
* `--from PATH`: For gated/manual datasets: a local dir holding the file(s).
* `--offline / --no-offline`: Refuse network (default: on if HPC_ODA_OFFLINE=1).
* `-y, --yes`: Proceed even when the download size is unknown.
* `--help`: Show this message and exit.

### `hpc-oda datasets characterize`

Check a prepared table's health, choose its benchmark window, write its runtime card.

Writes `<stem>.card.json` under --out. `recipes write`, `bench-matrix`, `datasets ceiling
--card` and the leaderboard read it; people read it on the dataset's card, so run
`hpc-oda datasets cards` after. See docs/benchmarking/runtime/methodology.md.

**Usage**:

```console
$ hpc-oda datasets characterize [OPTIONS] TABLE_PATH
```

**Arguments**:

* `TABLE_PATH`: Canonical oda.job parquet to characterize.  [required]

**Options**:

* `--out PATH`: Output directory for the runtime card (*.card.json).  [default: docs/benchmarking/datasets]
* `--dataset-id TEXT`: Dataset id label (default: derived from the path).
* `--system TEXT`: System name recorded on the card.
* `--descriptor TEXT`: Descriptor id/path recorded on the card.
* `--pin-end TEXT`: Keep the window ending on this day (YYYY-MM-DD) instead of choosing one: the window a benchmark already ran on.
* `--anchor FLOAT`: Place the window END at this fraction of the healthy span.  [default: 0.8]
* `--train-days INTEGER`: Training lookback (days).  [default: 60]
* `--test-days INTEGER`: Test coverage (days).  [default: 90]
* `--history-days INTEGER`: History the earliest scored window must see (the lookback budget).  [default: 120]
* `--gap-min-days INTEGER`: Consecutive low-volume days that count as a missing block.  [default: 3]
* `--gap-floor FLOAT`: Missing-block threshold, as a fraction of median daily volume.  [default: 0.05]
* `--help`: Show this message and exit.

### `hpc-oda datasets cards`

Write a card for every dataset, generated from its files.

Each card comes from the dataset's descriptor, its runtime card, the error ceilings, the
recipes and the leaderboard, so regenerate the cards whenever one of those changes; for
the bundled datasets a unit test fails when the committed cards differ from what this
writes. With --descriptors, it cards a dataset of your own the same way.

**Usage**:

```console
$ hpc-oda datasets cards [OPTIONS]
```

**Options**:

* `--out PATH`: Directory to write the dataset cards into.  [default: docs/datasets/cards]
* `--leaderboard PATH`: The leaderboard JSON the cards' results come from.  [default: site/leaderboard/leaderboard.json]
* `--descriptors DIRECTORY`: Card the descriptors in this folder, your own among them, instead of the bundled ones.
* `--benchmark-dir PATH`: Folder of runtime cards (*.card.json) and error ceilings (*.ceiling.json).  [default: docs/benchmarking/datasets]
* `--recipes PATH`: A folder of the datasets' recipes (repeatable).
* `--help`: Show this message and exit.

### `hpc-oda datasets ceiling`

Compute the minimum error any submit-time predictor could achieve on this table.

Jobs with identical submit-time features cannot be told apart, so the best possible
prediction per signature is its group median (for MAE) or mean (for RMSE). That bound
calibrates every model score: an MAE means little without knowing how much accuracy was
available. Also measures causal memorization -- predicting from same-signature jobs that
finished earlier -- across a range of lookbacks, which is a deployable strategy rather
than a bound. See docs/benchmarking/runtime/ceilings.md.

**Usage**:

```console
$ hpc-oda datasets ceiling [OPTIONS] TABLE_PATH
```

**Arguments**:

* `TABLE_PATH`: Windowed oda.job parquet to analyse.  [required]

**Options**:

* `--out PATH`: Write the analysis JSON here (default: beside the table).
* `--card PATH`: The dataset's runtime card (*.card.json): sets --n-windows to cover its test days. The runtime leaderboard scores 120 windows today, so pass --n-windows 120 to match it.
* `--n-windows INTEGER`: Rolling windows (power: 89). Overrides --card.
* `--test-window-hours INTEGER`: Hours in each rolling test window.  [default: 6]
* `--skip-windows INTEGER`: Leading windows with jobs to leave unscored: the walk-forward burn-in, so the floor covers the rows a runtime leaderboard score does. Power has one arm and no burn-in: pass 0.  [default: 20]
* `--dataset-id TEXT`: Label recorded on the analysis.
* `--target TEXT`: Column the floor bounds, e.g. avgpcon_per_node.  [default: runtime_seconds]
* `--extra-feature TEXT`: A column some benchmarked model reads beyond the shared allowlist (repeatable), e.g. embedding. The floor bounds a model only if its signature holds every input.
* `--start TEXT`: Read only the recipe's window: its first day.
* `--end TEXT`: Read only the recipe's window: its last day.
* `--require-nonnull TEXT`: Read only rows that have this column, as the recipe does (repeatable).
* `--by TEXT`: overlap: keep jobs that overlap the window; submit: keep jobs submitted in it.  [default: overlap]
* `--help`: Show this message and exit.

### `hpc-oda datasets slice`

Cut a prepared table to a window you name, keeping every job that overlaps it.

The rolling split tests the days before a table's last submit, so cutting the end
picks the test period, and the start must leave the training lookback. A job is kept
if it was submitted by the end of --end and ended on or after --start, as in
`bench-matrix slice`. Writes slice.json beside --out.

**Usage**:

```console
$ hpc-oda datasets slice [OPTIONS] TABLE_PATH
```

**Arguments**:

* `TABLE_PATH`: Canonical oda.job parquet to slice.  [required]

**Options**:

* `--start TEXT`: First day kept, YYYY-MM-DD (UTC, inclusive).  [required]
* `--end TEXT`: Last day kept, YYYY-MM-DD (UTC, inclusive).  [required]
* `--out PATH`: Output parquet path.  [required]
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix`

Plan the full model x dataset benchmark for an HPC cluster.

**Usage**:

```console
$ hpc-oda bench-matrix [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `plan`: Generate the benchmark-matrix plan...
* `slice`: Slice each dataset's canonical parquet to...
* `stage`: rsync the windowed parquets and the plan...
* `submit`: Submit embed jobs then benchmark cells...
* `status`: Poll sacct for the submitted jobs and...
* `collect`: rsync the cluster's result bundles (runs/)...
* `aggregate`: Build the leaderboards (index.html,...
* `rank`: Rank each cell by walk-forward choice...

### `hpc-oda bench-matrix plan`

Generate the benchmark-matrix plan (recipes + sbatch scripts + plan.json).

Each recipe tests its card's whole test period (360 6-hour windows for a 90-day card).
The runtime leaderboard counts 120 windows today, so these runs show on runs.html only.

**Usage**:

```console
$ hpc-oda bench-matrix plan [OPTIONS]
```

**Options**:

* `--cards-dir PATH`: Directory of runtime cards (*.card.json).  [default: docs/benchmarking/datasets]
* `--site PATH`: Local (gitignored) HPC site config.  [default: .hpc_oda/hpc-site.yml]
* `--out PATH`: Staging root for generated recipes/scripts.  [default: .hpc_oda/bench-matrix]
* `--plan-id TEXT`: Plan id (default: timestamp). Names the staging subdir.
* `--exclude-model TEXT`: Leave a model out of the matrix, by name, e.g. mlp (repeatable).
* `--include-unhealthy`: Include datasets whose window is flagged unhealthy.
* `--windows-dir PATH`: Sliced windows dir, read for each slice.json so cells are sized from the rows they actually load rather than the card's narrower window.  [default: .hpc_oda/bench-matrix/data/windows]
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix slice`

Slice each dataset's canonical parquet to its benchmark window.

Reads the canonical parquet named on each card and writes
`<out>/<dataset>/data.parquet`, plus a slice.json recording which window it
holds. That tree rsyncs to `<repo>/data/windows` on the cluster, where the generated
recipes read it. Overlapping (long-running) jobs are kept so the earliest rolling
windows keep their training rows — see the slice module.

By default each dataset is extended back by its card's history budget beyond the
training days (history_days - train_days), so a slice holds the history every lookback
arm can use. Deriving it rather than passing it by hand is deliberate: a slice silently
narrower than the split is invisible in the results.

**Usage**:

```console
$ hpc-oda bench-matrix slice [OPTIONS]
```

**Options**:

* `--cards-dir PATH`: Directory of runtime cards (*.card.json).  [default: docs/benchmarking/datasets]
* `--out PATH`: Local staging dir for windowed parquets (rsync to repo/data/windows).  [default: .hpc_oda/bench-matrix/data/windows]
* `--dataset TEXT`: Slice only this dataset (default: all healthy datasets).
* `--include-unhealthy`: Also slice datasets whose window is unhealthy.
* `--extra-lookback-days INTEGER RANGE`: Extend the slice earlier by N days, leaving the test region alone. Defaults to each card's history budget beyond its training days (history_days - train_days). Pass a value only to override that.  [x>=0]
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix stage`

rsync the windowed parquets and the plan (recipes + scripts) to the cluster.

**Usage**:

```console
$ hpc-oda bench-matrix stage [OPTIONS]
```

**Options**:

* `--plan-dir PATH`: Plan dir (default: newest under .hpc_oda/bench-matrix).
* `--site PATH`: Local (gitignored) HPC site config.  [default: .hpc_oda/hpc-site.yml]
* `--windows-dir PATH`: Local sliced windows to stage.  [default: .hpc_oda/bench-matrix/data/windows]
* `--dry-run`: Print commands without running them.
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix submit`

Submit embed jobs then benchmark cells (embedding_knn cells depend on their embed).

Dry-run by default; pass --execute to really submit. Use --only/--only-model
and --partition debug for a quick single-cell smoke before the full fleet.

--resume recovers an interrupted submit: it asks sacct which of the plan's job
names already exist and submits only the rest.

**Usage**:

```console
$ hpc-oda bench-matrix submit [OPTIONS]
```

**Options**:

* `--plan-dir PATH`: Plan dir (default: newest under .hpc_oda/bench-matrix).
* `--site PATH`: Local (gitignored) HPC site config.  [default: .hpc_oda/hpc-site.yml]
* `--execute`: Really submit, which charges the allocation (default: a dry run).
* `--only TEXT`: Submit only this dataset.
* `--only-model TEXT`: Submit only this model (short tag, e.g. baseline).
* `--partition TEXT`: Override partition (e.g. debug for a smoke test).
* `--time TEXT`: Override walltime (e.g. 00:20:00).
* `--resume`: Submit only cells that have no job yet (diffs the plan against sacct).
* `--chunk-size INTEGER`: Cells per SSH round-trip.  [default: 50]
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix status`

Poll sacct for the submitted jobs and summarize their states.

**Usage**:

```console
$ hpc-oda bench-matrix status [OPTIONS]
```

**Options**:

* `--plan-dir PATH`: Plan dir (default: newest under .hpc_oda/bench-matrix).
* `--site PATH`: Local (gitignored) HPC site config.  [default: .hpc_oda/hpc-site.yml]
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix collect`

rsync the cluster's result bundles (runs/) back locally.

**Usage**:

```console
$ hpc-oda bench-matrix collect [OPTIONS]
```

**Options**:

* `--plan-dir PATH`: Plan dir (default: newest under .hpc_oda/bench-matrix).
* `--site PATH`: Local (gitignored) HPC site config.  [default: .hpc_oda/hpc-site.yml]
* `--dest PATH`: Local dir for pulled result bundles (default: <plan-dir>/collected-runs).
* `--dry-run`: Print commands without running them.
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix aggregate`

Build the leaderboards (index.html, runs.html, leaderboard.json) from collected bundles.

**Usage**:

```console
$ hpc-oda bench-matrix aggregate [OPTIONS]
```

**Options**:

* `--plan-dir PATH`: Plan dir (default: newest under .hpc_oda/bench-matrix).
* `--runs PATH`: Collected runs dir (default: <plan-dir>/collected-runs).
* `--out PATH`: Leaderboard output dir (default: <plan-dir>/leaderboard).
* `--help`: Show this message and exit.

### `hpc-oda bench-matrix rank`

Rank each cell by walk-forward choice among its training-lookback arms.

Reporting the best arm by test error would select on the number it reports; this chooses
each window's arm from earlier windows only.

**Usage**:

```console
$ hpc-oda bench-matrix rank [OPTIONS]
```

**Options**:

* `--plan-dir PATH`: Plan dir (default: newest under .hpc_oda/bench-matrix).
* `--runs PATH`: Collected runs dir (default: <plan-dir>/collected-runs).
* `--out PATH`: Ranking output dir (default: <plan-dir>/leaderboard).
* `--metric TEXT`: Metric to select and score on (mae, rmse).  [default: mae]
* `--burn-in INTEGER`: Windows used to build history before scoring starts.  [default: 20]
* `--help`: Show this message and exit.

### `hpc-oda models`

Commands about the registered models.

**Usage**:

```console
$ hpc-oda models [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `cards`: Write a card for every registered model,...

### `hpc-oda models cards`

Write a card for every registered model, generated from the code.

Each card comes from the registry, the benchmark runners, the bundled recipes and the
leaderboard, so regenerate the cards whenever one of those changes; a unit test fails
when the committed cards differ from what this writes.

**Usage**:

```console
$ hpc-oda models cards [OPTIONS]
```

**Options**:

* `--out PATH`: Directory to write the model cards into.  [default: docs/models]
* `--leaderboard PATH`: The leaderboard JSON the cards' results come from.  [default: site/leaderboard/leaderboard.json]
* `--help`: Show this message and exit.

### `hpc-oda recipes`

Write the benchmark's recipes for a dataset of your own.

**Usage**:

```console
$ hpc-oda recipes [OPTIONS] COMMAND [ARGS]...
```

**Options**:

* `--help`: Show this message and exit.

**Commands**:

* `write`: Write every model's recipes for a dataset,...

### `hpc-oda recipes write`

Write every model's recipes for a dataset, on the benchmark's own protocol.

Runtime recipes need the dataset's runtime card, which sets their window; power recipes
are written for each per-node power target the descriptor maps, over the whole table or
the window you give. On `hpc-oda leaderboard`, the power runs count when you pass this
folder with --recipes, and the runtime runs count when --ceilings holds the runtime card.

**Usage**:

```console
$ hpc-oda recipes write [OPTIONS] DESCRIPTOR
```

**Arguments**:

* `DESCRIPTOR`: The dataset's descriptor (.yml).  [required]

**Options**:

* `--out PATH`: Folder to write the recipes into.  [required]
* `--card PATH`: The dataset's runtime card (from `datasets characterize`). Without it, no runtime recipes are written.
* `--start TEXT`: Power window: its first day, YYYY-MM-DD.
* `--end TEXT`: Power window: its last day, YYYY-MM-DD.
* `--by TEXT`: Power window. overlap: keep jobs that overlap it; submit: keep jobs submitted in it.  [default: overlap]
* `--require-nonnull TEXT`: Power: read only rows with this column (repeatable).
* `--runs-dir TEXT`: Where the runs write their result bundles.  [default: runs]
* `--model TEXT`: Write only this model's recipes (repeatable).
* `--help`: Show this message and exit.
