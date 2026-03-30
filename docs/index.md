# hpc-oda-commons Documentation

**HPC ODA Commons** is a community-driven platform for standardizing HPC operational data analytics. v0.1 focuses on SLURM job runtime prediction.

## Where to Start

**I want to try it out** -- [Quickstart](how-to/quickstart.md) (10 minutes, no data required)

**I have data to ingest** -- [Ingest slurmctld logs](how-to/ingest-slurmctld.md) | [Ingest Parquet exports](how-to/ingest-jobs-parquet.md)

**I want to understand results** -- [Interpreting Results](how-to/interpret-results.md)

**I want to contribute** -- [Contributing](how-to/contribute.md) | [Add a Model](how-to/add-model.md)

**I need a reference** -- [CLI Reference](reference/cli.md) | [Recipes](reference/recipes.md) | [Schema Versions](reference/schema-versions.md)

**I want to understand the design** -- [Benchmarks](concepts/benchmarks.md)

## 10-Minute Workflow

```bash
pip install -e ".[dev]"
hpc-oda init
hpc-oda browse
HPC_ODA_OFFLINE=1 hpc-oda run-baseline
hpc-oda ingest slurmctld --path /path/to/slurmctld.log
hpc-oda validate data/ingested/slurmctld/<run>/data.parquet
hpc-oda analyze --data data/ingested/slurmctld/<run>
HPC_ODA_OFFLINE=1 hpc-oda benchmark hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

See the [Quickstart guide](how-to/quickstart.md) for a walkthrough of each step.
