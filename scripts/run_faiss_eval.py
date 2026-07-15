#!/usr/bin/env python3
"""Script to run the FAISS/torch evaluation smoke test.

Usage:
  python3 scripts/run_faiss_eval.py
"""

from hpc_oda_commons.models.job_runtime_faiss import eval as faiss_eval


def main() -> int:
    faiss_eval.smoke_test()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
