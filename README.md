# hpc-oda-commons

_A community hub for **HPC Operational Data Analytics (ODA)** — built for clarity, comparability, and fast adoption._

> **Status:** early-stage, community-driven initiative (v0.1 in development).  
> **Founding collaborators:** NREL, NERSC, and BSC.  
> **Open source:** public, permissive licensing; contributions welcome and encouraged.

## What this aims to be
**hpc-oda-commons** is a public, open repository that will make ODA research and practice **discoverable, standardized, and reproducible**. It brings together a curated index of **models, datasets, and tools/instrumentation**, a shared set of **standards + benchmarks + leaderboards**, and a simple **tooling path** to run the same benchmarks on **your own data**, so results are apples-to-apples across sites.

## The three pillars
- **Find** — a central place to discover **models, datasets, and tools** (e.g., XDMoD, LDMS, Darshan, schedulers/simulators, digital twins, controllers) relevant to HPC ODA.  
- **Compare** — community **standards, benchmarks, and leaderboards** so results are measured the same way.  
- **Run** — a straightforward toolchain to **execute benchmarks on your own data** and produce reproducible, evidence-backed results.

> Goal: **standardize and unify** this domain — and help each other turn ideas into practice.

## The initial user experience we’re targeting (~10 minutes)
1. **Browse** the registry to pick a task (e.g., runtime or queue-time prediction).  
2. **Run** a baseline on a public dataset to see the metrics we all use.  
3. **Point** the same benchmark at your local logs (kept on-site) to get **comparable results** you can share internally.

## Who this is for
- **Site operators & sysadmins** — evaluate ideas on local data with minimal plumbing.  
- **Researchers & vendors** — submit models once and compare fairly across datasets and sites.  
- **Program managers** — track progress with transparent, reproducible leaderboards.

## Contribute
- Add a **dataset, model, or tool card** (link-first, with immutable references and SPDX license info).  
- Propose a **benchmark** (task, metrics, and minimal baseline).  
- Share a **result card** to update the leaderboard via PR.  
We welcome early contributors from across the community. Please open an issue to get involved.

> Note: the tools registry is **link-first** and non-endorsement; it’s for discoverability and interoperability signals.

---

**This repo complements the BoF series on AI for HPC Workload Analytics** — the BoF sets community priorities; **hpc-oda-commons operationalizes them** with shared artifacts and repeatable results.
