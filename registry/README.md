# Registry

The registry snapshot provides offline discovery for the Find pillar.

## Snapshot Files

- `registry/snapshot.json` is the source of truth for v0.1.
- `src/hpc_oda_commons/registry/snapshot.json` is the packaged copy.

## Updating the Snapshot

Use the helper script to validate and sync:

```bash
python scripts/build_registry_snapshot.py
```
