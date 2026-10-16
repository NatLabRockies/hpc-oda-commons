# Public sources of per-job power data

An audit, done 2026-10-16, of where per-job power can come from for job-power prediction
([#204](https://github.com/NatLabRockies/hpc-oda-commons/issues/204)). The target is
**average and peak power per node**. A source is only useful if it ties power to
a job, either directly or through a node + time join to a job table.

**How it was checked.** "Verified" means we read the real data: schemas, value ranges,
scaling with node count, and agreement between columns. "Reported" means the source's own
documentation or a small sample, as found by the research pass, without our own end-to-end
check. Anything neither of those confirmed is marked unconfirmed.

## Summary

| Source | System, span | Jobs | Average | Peak | Status |
|---|---|---|---|---|---|
| F-DATA | Fugaku, 2021-03 to 2024-04 | ~24M | yes | yes¹ | **Mapped** (`fdata_fugaku`, `fdata_fugaku_uopc`) |
| PM100 | Marconi100, May–Oct 2020 | 231k | yes | yes² | **Mapped** (`pm100`) |
| NLR Eagle Jobs (+ energy) | Eagle, 2018-11 to 2024-06 | ~13.8M | yes | via join³ | **Mapped**, average only (`nlr_eagle`) |
| LLNL LAST (Lassen) | Lassen, 2018-08 to 2020-11 | ~1.47M | yes | no | Registered (`lassen`), power **not mapped yet** (needs a join) |
| Adastra 15-day | Adastra MI250, 2024-08/09 | 15k | yes | no | Registered (`adastra_mi250`), power **not mapped yet** (needs cleaning) |
| NLR Kestrel Jobs | Kestrel, 2023-08 to 2025-12 | ~11M | yes⁴ | no | **Mapped**, average only, CPU nodes (`nlr_kestrel`) |
| M100 ExaData | Marconi100, 2020-03 to 2022-09 | all jobs | yes | yes | Not registered; 49.9 TB, node + time join |
| C6EnPLS | CRESCO6, 2023-11 to 2024-01 | 7k | yes | yes² | Not registered; one workload type |
| SURF Lisa | Lisa, 2022-06 to 2022-11 (power) | — | yes | yes | Not registered; Slurm × Prometheus join, shared nodes |
| NLR Peregrine | Peregrine, before 2015-10 | 10k + 1 month | yes | yes | Not registered; older system |
| HPC-JEEP (ARCHER2, COSMA8), Kabré | 2021–2025 | — | yes | no | Not registered; Slurm `ConsumedEnergy` only |
| Adastra 30-day, 90-day | Adastra, 2024 / 2026 | 43k / 111k | yes | 90-day: yes | Not registered; conventions differ per release |
| MIT Supercloud | TX-GAIA, 2021 | 98k GPU jobs | GPU only | GPU only | Registered for runtime; GPU power at 100 ms, no node power |
| NLR GenAI Power | Kestrel H100, 2025 | ~dozens | GPU + CPU | GPU + CPU | Not registered; tiny, no whole-node power |

¹ The mean of each node's maximum, not the peak of the job's total.
² The peak of the job's total power across nodes, divided by nodes.
³ Eagle Node Power (1-minute iLO readings per node) joined on `nodelist` and time.
⁴ Slurm energy, total over the job's nodes. On a shared node it is the node's energy, so those jobs get no power target.

**Peak power does not mean the same thing everywhere.** F-DATA's `maxpcon` is the sum of
each node's own peak; PM100 and C6EnPLS give the peak of the summed trace. These differ
when nodes peak at different times, so peak results should not be pooled across datasets
without noting it.

## Verified

- **F-DATA (Fugaku).** `avgpcon`, `maxpcon`, `nnumr`, `nnuma` and `nnumu` are present in
  every monthly file we read (2023-07, 2024-04). The data paper's Table 2 defines the power
  columns as sums over the job's nodes (reported). They sum the nodes the job runs on, not
  the allocated count: in April 2024, 49,877 jobs request 1 node and 48 cores, use 1 node,
  draw ~91 W, and show `nnuma` = 48; where `nnumu` < `nnuma`, power per used or requested
  node has a median of ~93 W against 43 W per allocated node. So per node is `÷ nnumr`. `econ` is energy in Wh (reported). F-DATA also ships a
  per-job `embedding`. Mapped in both Fugaku descriptors.
- **PM100.** `node_power_consumption` is the job's total node power in W across its nodes,
  sampled every 20 s. It scales linearly with node count (about 690–770 W per node from 1 to
  14 nodes). The authors' extraction code sums `ps0`+`ps1` input power per timestamp
  (reported). Mapped with `list_mean`/`list_max` ÷ allocated nodes, and checked against the
  raw traces on the real file.
- **NLR Eagle.** The job file `nlr_eagle` already downloads carries
  `node_energy_total_watt_hours`. Wh × 3600 ÷ seconds ÷ `nodes_used` gives 211–701 W per
  node (median 436 W) for June 2024. It agrees exactly (ratio 1.0000 over 9,561 jobs) with
  the per-node averages in the separate 1.3 GB energy variant. Of the 32,448 June-2024
  rows, 13,699 have energy, 18,704 have none and 45 read 0 Wh, which is no reading.
  Coverage is reported to thin out late in Eagle's life. The energy variant adds per-node
  and per-GPU arrays; 0 W in an array means no reading. Mapped (#206) as `energy_joules`
  (`type: energy`, `null_values: [0]`) ÷ runtime ÷ `nodes_used`; prepared through the
  descriptor, June 2024 matches the energy variant's per-node averages exactly (ratio
  1.000000 over 12,858 jobs).
- **LLNL LAST (Lassen).** `final_csm_allocation_node_history.csv` has one row per node per
  allocation, with `energy` in J. The IBM CSM docs define it as "total energy used by the
  node during the allocation". Energy ÷ (end − begin) gives 342–1,430 W per node (median
  532 W) on the AC922 nodes; `gpu_energy` gives a median of 192 W. Node rows match
  `num_nodes` exactly. Average only. Reported caveat: in the earliest rows GPU energy
  appears to be written to `gpu_usage`.
- **Adastra 15-day.** Undocumented at the source. `node_power_consumption` holds exactly one
  value per allocated node, that node's energy in J over the job (it grows with run time,
  r = 0.89). Value ÷ run time gives a median ~1.1–1.3 kW per node. 214 of 15,285 jobs read 0
  and some read a few watts: missing telemetry that needs to become null. The CPU and memory
  columns are placeholders (exactly 140 W and ~74 W × run time).
- **MIT Supercloud.** Per-job GPU CSVs carry `power_draw_W` (and `power_limit_W`) per GPU at
  100 ms. The CPU series and node data have no power, and Slurm's energy TRES is not
  populated. GPU power only.

## Reported

- **NLR Kestrel Jobs** (data.nlr.gov 302, DOI 10.7799/3023270), verified since (#209):
  `consumed_energy_raw_joules` is the Slurm job energy summed over nodes. Average per node
  = energy ÷ elapsed ÷ `nodes_used`. 81% (June 2024) and 73% (June 2025) of jobs have
  non-zero energy; GPU jobs have none. On a shared node it is the node's energy (a 1-core
  job reads ~650 W), so power is null for jobs that shared their node
  (`shared_job_count` ≥ 1, or a `shared*` partition). That leaves 86.6% / 67.8% of the
  rows kept for runtime, median 510 / 664 W per node. There is no public Kestrel
  node-power series.
- **NLR Eagle Node Power** (288, 10.7799/3015211): `dv` (node), `vl` (W) every minute,
  2019-04 to 2024-08, about 7.2 GB. Timestamps are local Mountain time with no zone, and 0 W
  means no reading. Joining to Eagle jobs on `nodelist` and time would give per-node peak.
- **NLR Eagle GPU Node Metrics** (301): 6 GPU nodes only. **NLR Peregrine** (235): per-node
  iLO power series (about 10 s) embedded in each job record, 10k jobs plus April 2015.
  Timestamps are milliseconds despite the docs. **NLR GenAI Power** (312): NVML/RAPL at
  5 Hz for a few dozen LLM jobs; GPU and CPU socket only. **NLR PUE** (300): facility-level.
- **M100 ExaData** (Zenodo 7588815 and siblings, Sci Data doi:10.1038/s41597-023-02174-3):
  IPMI `total_power`, `ps0/ps1_input_power` (W, 20 s per node) and per-GPU power, with a
  `job_table` that joins on node and time. 49.9 TB. PM100 is its 2020 extract.
- **C6EnPLS** (Zenodo 14135916, GitHub Reference-IMe/C6EnPLS): `jobs_info.csv` has
  `mean_sys_power` and `max_sys_power` (W, summed over the job's nodes) and energy in kWh,
  plus ~1 s per-node sensors. 7,235 jobs, all linear solvers.
- **SURF Lisa** (Zenodo 13685426): `node_power_usage` (W), per-GPU power, RAPL, every 30 s,
  joinable to Slurm by job ID, nodes and time. Nodes are often shared between jobs.
- **HPC-JEEP** (Zenodo 7128646: ARCHER2 `ConsumedEnergyRaw` per job step, COSMA8 IPMI) and
  **Kabré** (Zenodo 21463675: `ConsumedEnergyRaw`, requested nodes only): average only.
- **Adastra 30-day** (Zenodo 15536397) looks like average W per node and needs outlier
  cleaning. **Adastra 90-day** (Zenodo 21834931, 1.75 GB) has 20 s Cray pm_counters
  telemetry series, the most promising Adastra source; whether its series are per node or
  summed is unconfirmed.

## Not usable for per-job power

- **No job mapping:** OLCF Summit power and thermal (DOI 10.13139/OLCF/1861393; the job
  allocation history was never released), Google `powerdata_2019` (per PDU), AcmeTrace (no
  node list in its job traces), HPC-ODA (LRZ).
- **System level, benchmark or experiment only:** the LAST Power-Provisioning dataset
  (whole-system kW for seven systems), Frontier HPL, ALCF GEOPM experiments, Sandia HPCG
  Mutrino.
- **No power fields:** NREL Eagle on OEDI (5860), ATLAS (LANL), CC-IN2P3, IC2, ALCF DJC,
  the Parallel Workloads Archive, SNL Skybridge, Alibaba, Azure, Helios and Philly traces.
- **Not public:** NERSC Perlmutter/Cori job energy, and the European machines that record
  Slurm job energy without publishing it (LUMI, HLRS, JSC, BSC, LRZ, CSCS and others).
- **Unverified:** FRESCO. Its server returned an HTML page instead of the files during the
  audit, and the research found no power fields in its documentation.

## What it would take

In order of payoff for effort. Item 1 is
[#206](https://github.com/NatLabRockies/hpc-oda-commons/issues/206); the rest are tracked in
[#207](https://github.com/NatLabRockies/hpc-oda-commons/issues/207).

1. **NLR Eagle, average.** Done (#206): `type: energy`, `null_values` and chained ratio
   derives. Per-month coverage over the full ~13.8M jobs is still to be measured.
2. **NLR Kestrel, average.** Done (#209): the same energy mapping, with `null_when` to
   drop jobs that shared their node.
3. **Adastra 15-day, average.** `list_mean` ÷ runtime is expressible today, and
   `null_values: [0]` handles the zero readings. Near-zero readings (a few watts) need a
   threshold as well.
4. **Lassen, average.** Join the per-node energy file to the allocation table, which needs
   multi-file joins in the dataset pipeline.
5. **Peak beyond Fugaku and PM100.** Eagle Node Power joined on node and time (1 minute),
   M100 ExaData for 2020–2022, or the Adastra 90-day telemetry. Each is a bigger ingestion
   job with time-zone and missing-data handling.
6. **Small or specialised:** C6EnPLS, SURF Lisa, Peregrine, HPC-JEEP, Kabré, and GPU-only
   power from MIT Supercloud and GenAI.
