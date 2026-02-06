#!/usr/bin/env bash
# Manual golden path runner for v0.1 runtime prediction.
# Creates a temp project, runs DoD-1..DoD-4 commands, and prints output locations.

set -euo pipefail

ROOT="$(mktemp -d)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
echo "Using temp project: ${ROOT}"

cd "${ROOT}"
hpc-oda --help >/dev/null

hpc-oda init
HPC_ODA_OFFLINE=1 hpc-oda run-baseline

# Generate a minimal slurmctld log locally (avoid gitignored fixtures)
LOG_PATH="${ROOT}/slurmctld.log"
cat > "${LOG_PATH}" <<EOF
[2026-01-01T00:00:00.000] Allocate JobId=1 NodeList=node1 #CPUs=2 Partition=debug
[2026-01-01T00:01:00.000] _job_complete: JobId=1 done
EOF

HPC_ODA_OFFLINE=1 hpc-oda ingest slurmctld --path "${LOG_PATH}"
hpc-oda validate data/ingested/slurmctld/*/data.parquet
hpc-oda analyze --data data/ingested/slurmctld/*

# If the above cannot find repo fixture (depends where you run from), supply your own log path:
# hpc-oda ingest slurmctld --path /path/to/slurmctld.log

HPC_ODA_OFFLINE=1 hpc-oda benchmark "${REPO_ROOT}/recipes/job-runtime/baseline_tiny.yml"

echo "Outputs:"
find "${ROOT}" -maxdepth 3 -type f | sed 's|^| - |'
