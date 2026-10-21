# Benchmark your own data

This guide runs every model of the benchmark on job data of your own, the same way the
[published leaderboard](https://natlabrockies.github.io/hpc-oda-commons/leaderboard/) runs
them. At the end you have:

- every model's runtime prediction scored on your data, and its power prediction if your
  data records power;
- a private leaderboard, in the same form as the published one;
- a card describing your dataset;
- the result bundles behind them.

Everything runs on your own machine. Nothing is uploaded, and you choose what, if anything,
to share.

You can follow the guide first with a made-up export that ships with it, then repeat it with
your own data. The made-up export runs in about ten minutes on a laptop.
`tests/integration/test_benchmark_your_data_guide.py` runs this page's commands in that
order, so they work as written.

## Before you start

- **Install the toolkit** from a checkout of this repository ([install](install.md)). The two
  embedding-based models (Embedding + kNN and UoPC) also need the `embed` extra:
  `pip install -e ".[dev,embed]"`.
- **Make a project folder** to work in, and set `REPO` to your checkout. Every command below
  runs from the project folder.

<!-- not run by the test: it sets these itself -->
```bash
mkdir my-benchmark && cd my-benchmark
REPO=/path/to/hpc-oda-commons
```

- **What your data needs.** It needs one row per job, with:
  - submit, start and end times;
  - the runtime;
  - the fields known when a job is submitted: user, account, partition, QOS, job name, and
    the requested time, nodes and cores.

  Power is optional: either the job's energy or its average power, plus its node count.
- **How much data.** About seven months or more. The runtime window needs 120 days of history
  behind a 90-day evaluation. The leaderboard scores the last 30 days of that evaluation.
  The power benchmark tests the last 89 days with 60 days of history before them. With less
  data, the window shrinks, and the card says so.

The project folder ends up like this:

| Folder | What's in it |
|---|---|
| `exports/` | your export, never modified |
| `descriptors/` | the descriptor: what your export holds and how to read it |
| `data/` | the prepared table, and the windows and embedded tables made from it |
| `benchmark/datasets/` | the runtime card and the error ceilings |
| `recipes/` | one recipe per model, lookback and target |
| `runs/` | one result bundle per run |
| `leaderboard/`, `cards/` | your leaderboard and your dataset's card |

## 1. Export your jobs

To follow the guide with the made-up export, write it:

```bash
python "$REPO/docs/how-to/benchmark-your-data/make_example_export.py" exports
```

It holds 240 days of jobs from 30 users on an imaginary cluster, with energy readings.

For your own Slurm cluster, export the same fields with `sacct`. `-X` gives one line per
job, `-P` separates the fields with `|`, and `TZ=UTC` writes the times in UTC:

<!-- not run by the test: it needs a Slurm cluster -->
```bash
mkdir -p exports
TZ=UTC sacct -a -X -P -S 2025-01-01 -E 2025-08-31 \
  -o JobID,User,Account,Partition,QOS,JobName,Submit,Start,End,ElapsedRaw,TimelimitRaw,ReqNodes,NNodes,ReqCPUS,ConsumedEnergyRaw,State \
  > exports/my_cluster_sacct.txt
```

Other schedulers and formats work too. The data can be CSV or TSV, Parquet, the Standard
Workload Format or JSON, as long as there's one row per job.

## 2. Describe it

A descriptor says what the export holds and how to read it into the benchmark's job schema
(`oda.job.v0.2.0`). The bundled datasets are read the same way. Start from the example's:

```bash
mkdir -p descriptors
cp "$REPO/docs/how-to/benchmark-your-data/example_cluster.yml" descriptors/
```

[`example_cluster.yml`](benchmark-your-data/example_cluster.yml) is commented. For your own
data, copy it under your dataset's name, then change these:

- **`dataset_id`, `name`, `systems`:** your dataset's id (`dataset.<name>`), title and
  system. Use the same `<name>` for the file and for `output.id`.
- **`source.resources`:** your export's file name, its size in bytes and its SHA-256:

  <!-- not run by the test: it uses the example's file as it is -->
  ```bash
  shasum -a 256 exports/my_cluster_sacct.txt   # or sha256sum on Linux
  wc -c < exports/my_cluster_sacct.txt
  ```

  Preparing checks the file against these, so the prepared table is tied to this exact
  export.
- **`decode`:** the format, and for text, its delimiter.
- **`mapping`:** which export column feeds each schema column, and how to read it. The
  [mapping reference](ingest-jobs-parquet.md#mapping-spec-example) lists the transforms:
  timestamps, durations and their units, hashing, energy, derived ratios, and nulling bad
  readings. The bundled descriptors are worked examples:
  [`nlr_kestrel.yml`](../../src/hpc_oda_commons/datasets/descriptors/nlr_kestrel.yml) derives
  power from Slurm's energy counter, and
  [`pm100.yml`](../../src/hpc_oda_commons/datasets/descriptors/pm100.yml) reduces a power
  trace.

What the dataset can be used for comes from what it maps. With `runtime_seconds` mapped, it
serves runtime prediction. With `avgpcon_per_node` or `maxpcon_per_node`, the job's power per
node, it serves power prediction.

## 3. Prepare it, and check it

```bash
hpc-oda datasets prepare descriptors/example_cluster.yml --from exports
```

`--from` points at the folder holding your export. Preparing checks the export's checksum,
reads it, maps it, hashes the user and account names, and writes:

- `data/datasets/example_cluster/data.parquet`, the prepared table;
- `manifest.json` beside it: what went in and what was done to it;
- `data.parquet.quality.json` beside it: each column's share of missing values, rows whose
  start is after their end, and negative runtimes.

Read the quality report before going on. A column that's almost all missing usually means
its mapping names the wrong source column, or reads it in the wrong format.

## 4. Characterize it

```bash
hpc-oda datasets characterize data/datasets/example_cluster/data.parquet \
  --dataset-id dataset.example_cluster --system "Example Cluster" \
  --descriptor dataset.example_cluster --out benchmark/datasets
```

This writes `benchmark/datasets/example_cluster.card.json`, the dataset's runtime card:

- **The characterization:** the healthy span, the daily job counts, any missing blocks
  (outages, gaps in the export) and the runtime distribution.
- **The runtime window:** 60 days of training and a 90-day evaluation. The window ends at
  80% of the healthy span and is moved clear of any missing block. It is marked unhealthy
  if no clear window exists.

The runtime benchmark uses this window. Once a benchmark has run on it, keep it: if you
re-characterize after adding data, pass `--pin-end` with its end date and the window stays
put.

## 5. Write the recipes

```bash
hpc-oda recipes write descriptors/example_cluster.yml \
  --card benchmark/datasets/example_cluster.card.json --out recipes
```

A recipe is one run: a model, a dataset, a target and the evaluation. This writes every
model's recipes on the benchmark's own protocol:

- **`recipes/runtime/`:** each runtime model at each training lookback (10, 30 and 120
  days). Each is scored on the window's last 30 days, in 6-hour windows. The lookback each
  model uses is chosen walk-forward from the three, as on the leaderboard.
- **`recipes/power/`:** each power model for each per-node power target the descriptor maps.
  Each is scored on the table's last 89 days, a day at a time, with 60 days of history.

It also prints two sets of commands: the ones that build the embedded tables, and the ones
that compute the error ceilings. The next two steps run them.

Options:
- `--start`, `--end` and `--by`: run the power benchmark on a window instead of the whole
  table.
- `--require-nonnull`: read only rows that have a column.
- `--model`: write only some models.

## 6. Embed the jobs

Embedding + kNN and UoPC compare jobs by an embedding of each job's submission fields, so
they read a table that has one. Run the commands `recipes write` printed:

```bash
hpc-oda datasets slice data/datasets/example_cluster/data.parquet \
  --start 2025-01-01 --end 2025-07-29 --out data/windows/example_cluster/data.parquet
hpc-oda embed data/windows/example_cluster/data.parquet \
  --out data/embeddings/example_cluster/data.parquet \
  --model microsoft/harrier-oss-v1-0.6b --format prose
hpc-oda embed data/datasets/example_cluster/data.parquet \
  --out data/embeddings/example_cluster_power/data.parquet \
  --model microsoft/harrier-oss-v1-0.6b --format prose
```

The model is downloaded once and runs on a GPU if there is one, otherwise on the CPU.
Each distinct job description is encoded once, so it takes minutes, not hours. To try the
steps without downloading a model, use `--model stub`. Its embeddings carry no meaning,
though, so those two models' scores won't either.

## 7. Compute the error ceilings

An error ceiling is the lowest error any model could reach on these jobs, using only what's
known when a job is submitted. Jobs with identical submission fields can't be told apart, so
the best possible prediction for each group is its median. Headroom is measured against it.
Run the ceiling commands `recipes write` printed:

```bash
hpc-oda datasets ceiling data/datasets/example_cluster/data.parquet \
  --start 2025-01-01 --end 2025-07-29 --dataset-id dataset.example_cluster \
  --n-windows 120 --skip-windows 20 --out benchmark/datasets/example_cluster.ceiling.json
hpc-oda datasets ceiling data/embeddings/example_cluster_power/data.parquet \
  --target avgpcon_per_node --dataset-id dataset.example_cluster \
  --n-windows 89 --test-window-hours 24 --skip-windows 0 \
  --extra-feature embedding --extra-feature freq_req \
  --out benchmark/datasets/example_cluster.avgpcon_per_node.ceiling.json
```

They score exactly the jobs the leaderboard scores. On the made-up export they take
seconds; on millions of jobs, a few minutes.

## 8. Run the models

```bash
for recipe in recipes/runtime/*.yml recipes/power/*.yml; do
  hpc-oda benchmark "$recipe"
done
```

Each run writes one result bundle. The made-up export's 32 runs take about six minutes on a
laptop, MLP the longest. Time grows with the number of jobs. A dataset of a few million jobs
is better run on a cluster node: copy the project folder there and run the same loop, or
submit one job per recipe. Each run is independent. Add `-v` to `hpc-oda benchmark` to see
each window's progress.

Running a recipe again writes a new bundle. The leaderboard counts the newest bundle and lists
the older one as superseded.

## 9. Where the results are

```text
runs/example_cluster/<model>/lb10d/benchmark-<time>/   # runtime, one folder per lookback
runs/example_cluster/<model>/avg/benchmark-<time>/     # average power per node
    result.json       # the scores, the model, the dataset and its hash
    metrics.json      # every window's scores, and the exact settings the run used
    provenance.json   # the code version, packages, and the files read, with their hashes
```

[Interpret results](interpret-results.md) explains each file. A bundle records relative paths,
package versions and hashes. It doesn't hold your jobs.

## 10. Build your leaderboard

```bash
hpc-oda leaderboard --runs runs --out leaderboard \
  --ceilings benchmark/datasets --recipes recipes
```

`--ceilings` points at your runtime card and ceilings. `--recipes` makes the power runs from
your recipes count; bundled recipes count without it. Open the pages in a browser:

<!-- not run by the test: it opens a browser -->
```bash
open leaderboard/index.html   # xdg-open on Linux
```

`index.html` has one table per target, a row per model and a column for your dataset. It's
the same form as the published leaderboard. `runs.html` lists every run, and gives the reason
for any it didn't count: a run that isn't on the protocol, a lookback the card can't express,
or a missing ceiling.

## 11. Make your dataset's card

```bash
hpc-oda datasets cards --descriptors descriptors --benchmark-dir benchmark/datasets \
  --recipes recipes --leaderboard leaderboard/leaderboard.json --out cards
```

`cards/example_cluster.md` describes your dataset like the published
[dataset cards](../datasets/cards/README.md). It covers:
- its source;
- how it's curated and the columns it maps;
- the characterization and the runtime window;
- the error ceilings;
- every model's headroom and error;
- the recipes.

Regenerate it after new runs.

## 12. Read the results

- **Headroom** is the share of the possible improvement a model captures: (window mean's
  error − model's error) / (window mean's error − the ceiling).
  - 0% is no better than predicting each window's mean.
  - 100% reaches the ceiling.
  - A negative value, shown in red, is worse than the mean.

  Because it's measured against each dataset's own ceiling, headroom compares across
  datasets, unlike raw error. So you can set your dataset beside the published columns:
  if a model's headroom on your data is far below its published average, your jobs are
  harder for it.
- **MAE** is the average error in the target's units: a duration for runtime, and watts
  per node for power. Switch between headroom and MAE at the top of the page.
- **A cell without headroom** ("—") has an error but no headroom. The usual cause is that the
  run scored different jobs than the ceiling did, so the two aren't comparable: re-run the
  ceiling from step 7.
- **Average** is a model's mean headroom across the datasets in the table. With only your
  dataset it's that dataset's headroom.
- **Each model's card** (linked from its row) explains how it works and how it scores on the
  published datasets. [Interpret results](interpret-results.md#reading-the-leaderboard) has
  more.

The made-up export is made up: its scores say nothing about the models. And with
`--model stub` embeddings, Embedding + kNN and UoPC have nothing to learn from.

## Keeping it private

- **Nothing leaves your machine.** No command uploads data. The only downloads are the
  embedding model and, for bundled datasets, their public files.
- **Users and accounts are hashed while the export is read** (`type: hash_identifier`), so no
  user or account name reaches the prepared table. Set `HPC_ODA_HASH_SALT` to salt the hashes
  so they can't be matched against a list of names. Hash any other field that identifies
  someone in the same way.
- **What you could share holds no jobs:**
  - **Result bundles:** scores, settings, versions and hashes.
  - **Ceilings:** aggregates.
  - **Cards:** statistics such as row counts, date spans and how many distinct users there
    are.
  - **The leaderboard pages:** the cards' and bundles' content, self-contained.

  Read them before sharing.
- **Keep the project folder out of any repository.** In particular, never commit `exports/`
  or `data/`.
