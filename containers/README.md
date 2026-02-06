# Containers

Container files are provided for reproducible local runs and HPC environments.

## Docker

- `containers/Dockerfile` installs the project in editable mode and runs `hpc-oda --help`.

## Apptainer/Singularity

- `containers/apptainer.def` is a minimal definition for HPC sites.

These are intentionally simple for v0.1. Sites can adapt them to their
preferred base images and dependency pinning policies.
