FAISS-based offline evaluator
=================================

This document describes the FAISS-based exact evaluator added to the repository.

How to run (local dev)

1. Install runtime extras (optional):

```bash
python3 -m pip install -e .[faiss]
```

2. Run the smoke test (CPU path requires only `numpy`):

```bash
python3 scripts/run_faiss_eval.py
```

Implementation notes
- `src/hpc_oda_commons/models/job_runtime_faiss/eval.py` contains `evaluate_offline()` which implements exact top-k search using FAISS (IndexFlatIP) or a torch matmul fallback.
- The harness writes hardware detection info to `.hpc_oda_hardware.yaml` and `.hpc_oda_hardware.env` for reproducibility.
