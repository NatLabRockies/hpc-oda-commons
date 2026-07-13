#!/usr/bin/env python3
"""Script to run the FAISS/torch evaluation smoke test.

Usage:
  python3 scripts/run_faiss_eval.py
"""
import sys
from pathlib import Path

sys.path.insert(0, "src")

from hpc_oda_commons.models.job_runtime_faiss import eval as faiss_eval


def main():
    faiss_eval.smoke_test()


if __name__ == "__main__":
    main()
