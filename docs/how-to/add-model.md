# Add a Model

In v0.1, models are implemented as in-repo Python classes and referenced by
registry metadata and recipes.

## Minimal Steps

1. Implement a model class under `src/hpc_oda_commons/models/`.
2. Add a registry entry for the model in `registry/snapshot.json`.
3. Add a recipe that references the model (`recipes/`).
4. Add unit tests that exercise `fit()` and `predict()`.

## Required Metadata

The registry entry should include:
1. `id`
2. `name`
3. `version`
4. `problem_domain`
5. `input_schema_version`
6. `output_schema_version`
7. `supported_sources`

## Example

See `src/hpc_oda_commons/models/job_runtime_baseline/` for a reference model.
