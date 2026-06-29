# Contributing

The development process — workflow, environment, quality gate, branch naming,
coding standards, and branch protection — lives in
[`CONTRIBUTING.md`](../../CONTRIBUTING.md). Start there.

This page covers **where** to contribute and a couple of project-specific tasks.

## Ways to contribute

1. **Improve ingestion** -- enhance slurmctld parsing, add new adapters
2. **Add models** -- implement new prediction models ([guide](add-model.md))
3. **Add recipes** -- create benchmark recipes ([recipe format](../reference/recipes.md))
4. **Improve docs** -- expand guides, add examples

## Code integrity (record-hash)

After tests pass on a clean commit, register the source hash so future benchmark
results can verify they ran validated code:

```bash
hpc-oda record-hash
git add src/hpc_oda_commons/integrity/known_hashes.json
git commit -m "Record source hash"
```

Note: this certifies *code identity*, not numeric reproducibility of fitted-model
metrics across machines — see [`known-issues.md`](../known-issues.md).

## Schema changes

Schema changes require a Schema Evolution Request (SER): open an issue describing
the compatibility impact and migration plan before changing a versioned schema.
