# hpc-oda-commons Documentation

**HPC ODA Commons** is a community-driven platform for standardizing HPC operational data analytics. v0.1 focuses on SLURM job runtime prediction.

## Where to Start

**I want to try it out** -- [Quickstart](how-to/quickstart.md) (10 minutes, no data required)

**I have data to ingest** -- [Ingest Parquet exports](how-to/ingest-jobs-parquet.md) | [Ingest slurmctld logs](how-to/ingest-slurmctld.md)

**I want to understand results** -- [Interpreting Results](how-to/interpret-results.md)

**I want to contribute** -- [Contributing](how-to/contribute.md) | [Add a Model](how-to/add-model.md)

**I need a reference** -- [CLI Reference](reference/cli.md) | [Recipes](reference/recipes.md) | [Schema Versions](reference/schema-versions.md)

**I want to understand the design** -- [Benchmarks](concepts/benchmarks.md)

## 10-Minute Workflow

```bash
pip install -e ".[dev]"
hpc-oda browse
hpc-oda ingest jobs-parquet --path /path/to/jobs.parquet
hpc-oda validate data/ingested/jobs_parquet/<run>/data.parquet
hpc-oda benchmark my_recipe.yml
hpc-oda leaderboard --runs runs --out leaderboard
```

See the [Quickstart guide](how-to/quickstart.md) for a walkthrough of each step.
