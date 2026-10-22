# hpc-oda-commons

**A community-driven platform for standardizing HPC operational data analytics.**

HPC sites generate enormous volumes of operational data — scheduler logs, accounting records, monitoring streams — but turning that data into actionable insight is needlessly hard. Each site builds bespoke parsers, schemas, and evaluation pipelines. Results can't be compared across institutions. Promising analytics ideas stay siloed because there's no shared language for describing the data, the experiments, or the outcomes.

hpc-oda-commons fixes this by establishing **community-governed contracts** — versioned schemas, canonical artifacts, and benchmark recipes — that make ODA workflows **discoverable**, **reproducible**, and **comparable**. It pairs these standards with a practical, CLI-first toolkit that lets operators and researchers go from raw logs to standardized results without sending data off-cluster.

**Leaderboard:** <https://natlabrockies.github.io/hpc-oda-commons/leaderboard/>: the benchmarked models on public datasets, for job runtime and job power.

## Design Principles

- **Artifacts are the interface.** Every stage of the pipeline reads and writes stable, versioned artifacts (Parquet tables, JSON manifests, result bundles). Standards live in the artifact contracts, not in any particular tool's internals.
- **Local-first.** Ingestion and analysis run entirely on your machine. No data is uploaded or transmitted. Identifier hashing lets you sanitize artifacts before sharing.
- **Recipe-driven evaluation.** Benchmarks are defined by YAML recipes that fully specify dataset, model, metrics, and split strategy — so "running the same benchmark" actually means the same thing across sites.
- **Domain-extensible.** The platform is designed to support multiple ODA problem domains. Job runtime and job power prediction are benchmarked today; queue wait time and others can follow.

## The Three Pillars

| Pillar | Purpose |
|--------|---------|
| **Find** | Discover the models, datasets, recipes and adapters in the registry (`hpc-oda browse`, `hpc-oda info <id>`) |
| **Run** | Fetch and prepare datasets, ingest your own, and validate them against the schemas |
| **Compare** | Run recipe-driven benchmarks and gather the results into leaderboards |

Together, these let a site operator go from local logs to comparable, provenance-tracked results — and let a researcher publish results that others can actually reproduce.

## Getting started

Python 3.10 or later.

```bash
git clone https://github.com/NatLabRockies/hpc-oda-commons && cd hpc-oda-commons
pip install -e ".[dev]"

hpc-oda browse                         # the models, datasets and recipes
HPC_ODA_OFFLINE=1 hpc-oda run-baseline # a baseline on a bundled synthetic dataset
```

The [quickstart](docs/how-to/quickstart.md) walks through this in five minutes, and
[install](docs/how-to/install.md) covers the optional extras.

**Benchmark your own data.** [Benchmark your own data](docs/how-to/benchmark-your-data.md)
runs every model on your jobs the way the published leaderboard runs them, and builds a private
leaderboard and dataset card. Nothing leaves your machine, and a test runs the guide's commands,
so they work as written.

**Results.** Every [model](docs/models/README.md) and every [dataset](docs/datasets/cards/README.md)
has a card, generated from the code and the results. [Benchmarking](docs/benchmarking/README.md)
explains how the runtime and power tracks are run.

## Working with AI agents

The CLI is scriptable, recipes are declarative YAML, and every output is JSON, so an agent can
drive the whole workflow. Point it at [`CLAUDE.md`](CLAUDE.md) (also `AGENTS.md`). It asks
whether the agent is using or developing the tool, and routes to
[`docs/agent-usage.md`](docs/agent-usage.md) or to [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Documentation

[The documentation index](docs/index.md) is the map. The main references:

- [CLI reference](docs/reference/cli.md): every command and option, generated from the CLI.
- [Recipes](docs/reference/recipes.md) and [schema versions](docs/reference/schema-versions.md).
- [Architecture](docs/architecture.md): the data flow and the package layout.
- [Benchmarks](docs/concepts/benchmarks.md): split methods and how rolling evaluation works.
- [Interpreting results](docs/how-to/interpret-results.md): result bundles, provenance and the
  leaderboard.
- [`WHITEPAPER.md`](WHITEPAPER.md): the design and its rationale.
