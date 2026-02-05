# Python API

The v0.1 surface is CLI-first. Python APIs are minimal and focused on artifacts.
The CLI is the stable interface for v0.1; Python APIs are experimental.

## Kernel
1. `hpc_oda_commons.kernel.artifacts`
   Read/write ODA tables, manifests, and result bundles.
2. `hpc_oda_commons.kernel.validate`
   JSON schema validation helpers.
3. `hpc_oda_commons.kernel.schemas`
   Load bundled JSON schemas by ID.

## Schema
1. `hpc_oda_commons.schema.validator`
   Validation with semantic checks and quality reporting.
