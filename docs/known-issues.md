# Known Issues

## MAJOR — Cross-environment numeric reproducibility of fitted models

**Status:** open · **Severity:** major · **Affects:** XGBoost and TF-IDF kNN model outputs

### Summary

hpc-oda-commons positions reproducibility as a core guarantee: the same code on the
same data should produce the same result, and the integrity hash + critical-path
regression test are meant to certify that. **Today that guarantee does not hold for the
fitted models (XGBoost, TF-IDF kNN) across different machines.** The exact MAE/RMSE these
models produce depends on the CPU architecture, the compiled BLAS/SIMD build, and (under
emulation) the translation layer — not on the code or the data.

### Evidence

The critical-path regression test (`tests/unit/test_critical_path_regression.py`) runs all
three models on a fixed, deterministic 40-row dataset with fixed seeds and single-threaded
XGBoost (`n_jobs=1`, `random_state=42`). With **identical** package versions
(xgboost 3.2.0, scikit-learn 1.9.0, numpy 2.4.6) the XGBoost MAE differs by environment:

| Environment                         | XGBoost MAE | TF-IDF MAE |
|-------------------------------------|:-----------:|:----------:|
| macOS, Apple Silicon (arm64)        | 40.48       | 149.275    |
| Linux x86_64 (Docker, Rosetta-emul.)| 36.09       | 149.275    |
| Linux x86_64 (GitHub Actions CI)    | 32.48       | 140.64     |

The **baseline** model (a pure-Python mean predictor) produces an identical result in every
environment — proving the input data, splits, metric computation, and surrounding pipeline
are deterministic. The divergence lives entirely in the compiled numerics of XGBoost (C++
tree builder) and scikit-learn (BLAS-backed SVD / nearest-neighbour search).

### Why the difference is large (~10–25%), not tiny

A tree split and a kNN neighbour selection are **discrete** decisions. On a tiny dataset a
sub-ulp floating-point difference can flip one split threshold or one neighbour tie, which
changes every downstream prediction — turning a microscopic numeric difference into a
double-digit-percent MAE swing. With more data this averages out, but the regression test
deliberately uses a tiny dataset, which maximises the sensitivity.

### Current mitigation

- The exact-value assertions for XGBoost and TF-IDF in the critical-path test are marked
  `pytest.mark.xfail(strict=False)` so they do not gate CI, while remaining visible as known
  failures (they will XPASS on whatever environment happens to match the frozen constants).
- Portable guarantees are still asserted hard: the **baseline** MAE/RMSE is exact, and
  `test_all_models_same_splits` verifies all three models score the same windows/rows.

### Toward a real fix (later push)

Options to evaluate, roughly in order of preference:

1. **Pin a fully reproducible execution environment** for the regression guarantee — a fixed
   container image (OS + CPU baseline + locked BLAS + locked wheels + `PYTHONHASHSEED`) that
   CI and contributors run the exact-value check inside. The integrity-hash claim is only
   meaningful relative to such an environment.
2. **Quantify and bound** the cross-environment spread on a realistically sized dataset and,
   if acceptably small there, assert with a documented tolerance instead of exact equality.
3. **Investigate per-library determinism knobs** (XGBoost `tree_method`, deterministic SVD
   solver, thread pinning) — these reduce run-to-run variance but do **not** remove
   cross-architecture differences, so they are necessary-but-not-sufficient.

Until one of these lands, treat reproducibility as **verified for the baseline and the
data/split/metric pipeline, but not yet for the fitted-model metric values across machines.**
