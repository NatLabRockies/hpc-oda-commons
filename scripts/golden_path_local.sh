#!/usr/bin/env bash
# Manual golden path runner for v0.1 runtime prediction.
# Creates a temp project, runs DoD-1..DoD-4 commands, and prints output locations.

set -euo pipefail

ROOT="$(mktemp -d)"
echo "Using temp project: ${ROOT}"

cd "${ROOT}"
hpc-oda --help >/dev/null

hpc-oda init
HPC_ODA_OFFLINE=1 hpc-oda run-baseline

HPC_ODA_OFFLINE=1 hpc-oda ingest slurmctld --path "$(python -c 'import pathlib; print((pathlib.Path.cwd().parents[1] / "tests/fixtures/slurmctld.log").resolve())' 2>/dev/null || true)"

# If the above cannot find repo fixture (depends where you run from), supply your own log path:
# hpc-oda ingest slurmctld --path /path/to/slurmctld.log

HPC_ODA_OFFLINE=1 hpc-oda benchmark /path/to/repo/recipes/job-runtime/baseline_tiny.yml

echo "Outputs:"
find "${ROOT}" -maxdepth 3 -type f | sed 's|^| - |'
