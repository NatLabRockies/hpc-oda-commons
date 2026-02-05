# Benchmarks

Benchmarks define how models are evaluated against datasets to produce comparable results.

## Recipes
Recipes are YAML files that specify:
1. Dataset reference and schema version
2. Model reference and version
3. Metrics to compute
4. Optional split configuration

Example recipe path for v0.1:
`hpc_oda_commons/recipes/job-runtime/baseline_tiny.yml`

## Metrics
The runtime prediction baseline uses regression metrics:
1. MAE
2. RMSE

Additional metrics can be added as long as they are declared in the recipe.

## Result Bundles
Benchmarks produce a result bundle with:
1. `result.json`
2. `metrics.json`
3. `provenance.json`

Result bundles are the input to the leaderboard generator.
