# Artifacts

The v0.1 runtime-prediction slice produces three canonical artifact types.

## ODA Table (Parquet)

A table of job records that follows `oda.job.v0.1.0`. This is the primary input
for validation, baseline analysis, and benchmarks.

## Manifest (JSON)

A manifest captures provenance and transformations for an artifact. The ingest
command writes `manifest.json` alongside the parquet file.

Required elements:
1. `schema_version`
2. `inputs`
3. `artifact`
4. `provenance`
5. `transformations`

## Result Bundle (Directory)

Benchmark and baseline runs write a result bundle directory containing:
1. `result.json`
2. `metrics.json`
3. `provenance.json`

Result bundles are the input to leaderboard generation.

## Quality Report

`hpc-oda validate <parquet>` writes a `*.quality.json` report that includes
missingness and semantic checks (e.g., negative runtime or inverted timestamps).

## Analysis Report

`hpc-oda analyze` writes an `analysis.json` and a lightweight HTML report.
