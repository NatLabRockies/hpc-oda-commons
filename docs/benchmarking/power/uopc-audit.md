# UoPC audit — our implementation against the paper and the authors' code

**Status:** dev note, 2026-10-19. The [proposed work](#proposed-work) is tracked in
[#222](https://github.com/NatLabRockies/hpc-oda-commons/issues/222). Done:
- item 1, the corrections;
- item 2, the reproduction reruns ([results](uopc.md#variants-padded-jobs-and-node-count));
- item 3, scoped down to feature modes ([results](#feature-modes-measured)). It does not
  include the paper-style embedding.

`balanced` became UoPC's default (#227). Item 4, the F-DATA job-name ablation, was dropped
as unnecessary for now.

**Follow-up ([#228](https://github.com/NatLabRockies/hpc-oda-commons/issues/228)):** our
reproduction now uses only choices we can defend: per requested node, `balanced` features,
k = 20 (from the θ × k sweep on these settings), all jobs. With the vote it scored 7.82% /
R² 0.770 on average power and 8.06% / 0.754 on peak. The
authors' setup (per allocated node, `zscore`) is kept as a labelled comparison recipe. See
[Our choices, and why](uopc.md#our-choices-and-why).

**Follow-up ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)):** our UoPC predicts the median of its k neighbours'
values instead of the authors' vote over whole watts, in both protocols. The vote breaks
ties to the lowest neighbour, so it under-predicts wherever a user's jobs vary. The
paper-comparison recipes keep the vote. See
[The median of the neighbours, not a vote](uopc.md#the-median-of-the-neighbours-not-a-vote).
The tables below predate both follow-ups unless they say otherwise.

This note checks the Commons' UoPC against its sources, prompted by the question "did we
reproduce UoPC faithfully?". It covers both of our modes: the paper reproduction
(`split.method: cutoff`, [uopc.md](uopc.md)) and the rolling benchmark version
(`split.method: rolling`, [power results](results.md)).

## Summary

- **The reproduction follows the paper's evaluation protocol and matches its results.** That
  covers the test set, the history rule, θ = 500, k = 5 and skipped cold starts. The
  results: 9.93% MAPE / R² 0.837 against the paper's 10% / 0.80 on average power, and
  10.17% / 0.826 against 10% / 0.79 on peak.
- **The features differ.** The paper embeds the string "job name, cores, nodes, frequency,
  environment". We use F-DATA's precomputed embedding plus z-scored cores, nodes and
  frequency. That embedding is the same encoder over the original user, job name and
  environment. The z-scoring makes frequency a hard split and all but removes cores and
  nodes.
- **The node count is right in the reproduction and deliberately different in the benchmark.**
  The paper divides by allocated nodes (`nnuma`), and its figures confirm it. But its data
  lacks the ~150k most heavily padded test jobs that the public files contain, so our
  reproduction scores jobs the paper apparently did not.
- **The rolling benchmark UoPC differs further.** It uses a day-level history cutoff,
  per-requested-node targets, and an all-user fallback for cold starts.
- **Several statements in our docs and code are wrong.** Choices are attributed to "the
  authors' code" that appear in neither of the authors' repositories (see
  [Claims to correct](#claims-to-correct)).
- **An exact copy of the paper's embedding can't be built from public data.** The job names
  are anonymised. A paper-style approximation can be built, and is worth running as an
  encoding experiment.

## Sources

| Source | What it is |
|---|---|
| Antici, Borghesi, Domke, Kiziltan, *UoPC: A User-based Online Framework to Predict Job Power Consumption in HPC Systems*, ISC 2025, [doi:10.23919/ISC.2025.11017729](https://doi.org/10.23919/ISC.2025.11017729) | **The UoPC paper.** Full 12-page version read. |
| Antici, Borghesi, Kiziltan, Domke, Bartolini, *An online algorithm for power consumption prediction of HPC workload*, FGCS 175 (2026) 108064, [doi:10.1016/j.future.2025.108064](https://doi.org/10.1016/j.future.2025.108064) | Follow-up paper, referred to here as **JPCP**. It cites UoPC as [37] but does not describe it. Its "online algorithm" trains on all users and is close to our rolling protocol. |
| [francescoantici/UoPC](https://github.com/francescoantici/UoPC) at `e51217c` (2025-06-27); full history read back to `4e65c06` (2024-10-10) | A single-job command-line tool (`predict.py`). It has no evaluation harness, no F-DATA loader, no date cutoff, no per-node division and no scaling. |
| [francescoantici/online-jpcp](https://github.com/francescoantici/online-jpcp) at `081cc73` (2025-04-08) | The JPCP experiment code. |

The public UoPC README says "10% prediction error on more than 700k job data". The paper says
**more than 1.3 million jobs from more than 700 users**. The README seems to have garbled the
two.

## The four variants

| | **Benchmark UoPC** (rolling) | **Reproduction** (cutoff) | **UoPC paper** | **JPCP** |
|---|---|---|---|---|
| Whose jobs | The user only | The user only | The user only | All users |
| Test jobs | 89 daily windows, ~Feb 1–Apr 30 2024; 1.51M | Submitted from 2024-02-01; 1.59M | Submitted from Feb 1; >1.3M | Every day after the first α days |
| History for a test job | The user's jobs ending in the 60 days before the day's split | The user's jobs ending before this job's submission | Same as reproduction | All jobs ending in the α days before the day |
| Context | Newest θ = 500 | Newest θ = 500 | θ = 500, k = 5 (from θ ∈ {50…5000} × k ∈ {5, 10, 20, 50}) | All, α ∈ {15, 30, 45, 60} |
| Refit | Per user per day | Per job | Per job | Daily |
| Predictor | `KNeighborsClassifier` on rounded watts | Same | scikit-learn KNN, defaults (classifier in the code) | `KNeighborsRegressor`, RF, XGBoost, defaults |
| Target | Avg and peak **per requested node** | Avg and peak **per allocated node** | Per node (allocated; see below) | Min, avg and peak per allocated node, floored with `int()` |
| Features | F-DATA embedding + z-scored cores, nodes, frequency | Same | MiniLM embedding of "job name, cores, nodes, frequency, environment" | User, job name, cores, nodes, environment, frequency |
| Scaling fitted on | Each window's training rows | All five months, test included | None | None |
| Fewer than k history jobs | All-user window mean (0.86%) | Skipped (0.23%) | No prediction | — |
| F-DATA avg power | 11.36% / 0.660 | 9.93% / 0.837 | 10% / 0.80 | INT+RF 12% / 0.78; INT+KNN 16% / 0.67; SB+KNN 16% / 0.66 |
| F-DATA peak power | 11.73% / 0.629 | 10.17% / 0.826 | 10% / 0.79 | INT+RF 12% / 0.79 |

**The paper's baselines are all-user models retrained daily on 60 days:** A-RF 14% / 0.76
(average) and 15% / 0.76 (peak), and A-KNN 16% / 0.60 and 17% / 0.58. It also has a per-user
RF, which did not finish in a week, and a linear regression on the user's last 5 jobs, at
over 100% MAPE. A-RF is essentially our rolling protocol; our rolling Random Forest scores
11.10% / 0.776. Our reproduction uses per-user and global means as baselines instead.

**On PM100 the paper reports** UoPC at 18% / 0.11 on average power and 22% / 0.13 on peak,
against A-RF at 20% / 0.07 and 24% / 0.13. When this was written we had not run UoPC on
PM100; it has since run on the rolling protocol ([PM100](results.md#pm100)).

## Deviation 1 — node count

**The benchmark divides by requested nodes on F-DATA.** This changed from allocated nodes in
83405d7, during #204/#205, before the power runs. Allocated counts (`nnuma`) are padded
beyond the nodes a job runs on, but F-DATA's power sums only the nodes it ran on. Measured
over all five months (2.93M jobs):

| | Jobs with `nnuma` > requested (727,508, 24.8%) |
|---|---:|
| Nodes used (`nnumu`) = requested | 95.3% |
| Nodes used = allocated | 0.0% |
| Median W per requested / used / allocated node | 91.8 / 91.9 / **1.9** |
| Share below 20 W per allocated node | 71.6% |

The clearest case is 410,740 jobs that request 1 node and 48 cores, run on 1 node and draw
~92 W, yet record `nnuma` = 48. Jobs without padding have a median of 89.1 W per node.
Requested nodes are also known at submission, so a per-node prediction × requested nodes
gives a job's total before it runs.

**The paper divides by allocated nodes.** The text says power is "normalized on the number of
nodes" after summing over "the nodes allocated". The JPCP code divides by `nnuma`. The
figures confirm it. In the test period (jobs submitted from Feb 1):

- **Fig. 4 has small bars at ~11, ~15 and ~22 W** (~9.7k, ~5.5k and ~3.7k jobs). Per
  requested node our test period has no job below 20 W. Per allocated node we get 11 W
  (11.7k), 15 W (7.4k) and 22 W (4.5k), from jobs whose allocation is 8×, 6× and 4× their
  request.
- **Fig. 4's tallest bar** (~95k at 40 W) matches our 41 W bin (94.7k). So the figure appears
  to be this test period at 1 W bins.
- **There is no 90–93 W spike in Fig. 4.** Per requested node there would be one, of 175k
  jobs.
- **Fig. 11's [0, 20) W ground-truth box** sits at ~11–15 W.

**But the paper's data lacks the most heavily padded jobs.** Per allocated node, our test
period has 150,015 jobs below 5 W, with a ~135k bar at 1–2 W. That would be the
second-tallest bar in Fig. 4, and the figure's lowest bar is ~11 W. These are 139,074 jobs
with 1 node requested and `nnuma` = 48, plus 10,941 at 24×. Per requested node they would
form the missing 91 W spike instead. So the paper's export either lacks them or records
their `nnuma` differently. The JPCP code reads a non-Zenodo export (`CR-STR-*` column names,
UNIX timestamps), which supports this. We can't tell which.

**Consequences:**
- Dividing by allocated nodes matches the paper, but on the public files it gives ~150k jobs
  a ~2 W target the paper's data apparently never had. Since #228 our reproduction divides
  by requested nodes, and the paper's divisor is kept only for a labelled comparison.
- The paper-setup comparison scores ~150k jobs (9.4% of its test set) the paper apparently did not.
  They are easy to predict, because neighbours are padded the same way, so they inflate R².
  Excluding the 48× jobs gives 10.25% / 0.762 on average power and 10.51% / 0.746 on peak.
- Our numbers (benchmark and reproduction) are on a different target from both papers, by
  design.

## Deviation 2 — features and encoding

**The paper** concatenates the feature values into a comma-separated string and embeds it
with all-MiniLM-L6-v2 into 384 numbers. The features are job name, cores requested, nodes
requested, requested frequency and environment, with the user left out because each model
is per-user. The paper is internally inconsistent in three places:
- the example string `"user_1,job_1,48,1,env_1,2000"` includes the user and puts environment
  before frequency;
- the footnote links all-MiniLM-**L12**-v2;
- the text says the output is "normalized in the range [-1, 1]".

**F-DATA's precomputed `embedding` is all-MiniLM-L6-v2 over the original user, job name
and environment.** [F-DATA's generation script](https://github.com/francescoantici/F-DATA/blob/main/generation_scripts/generate_derived_features.py) (`generate_derived_features.py`) joins the unanonymised `usr`, `jnam`
and `jobenv_req` with commas, leaving out empty values, and encodes the string. The Zenodo
`feature_list.csv` describes the column as "Sensitive data encoding with Sentence-Bert".

The data agrees. On February 2024 (669,758 jobs, 38,637 distinct embeddings), the embedding
is almost a function of user + `jnam`:
- there are 37,946 such pairs; 709 have more than one embedding, and 19 embeddings span more
  than one pair;
- adding the environment changes almost nothing, because it barely varies within a user's
  job name (one pair has two environments);
- adding nodes creates 2,238 embeddings shared across keys, so the embedding doesn't change
  with nodes.

It is the only public carrier of the real job names' meaning. (An earlier version of this
note called it name-only and said environment was unused; both were wrong.)

**Our features** are that embedding (unit length) plus `num_cores_req`, `num_nodes_req` and
`freq_req`, each z-scored. The reproduction scales over all five months, which is a small
look-ahead in the feature scale only. The rolling mode scales over each window's training
rows. The scaling originates in #203's first commit ("Match Phase 1 exactly", meaning an
earlier implementation whose source isn't recorded). It is in neither the paper nor the
authors' repositories. Its effect on the distance between jobs, with standard deviations
over the prepared table:

| Feature | Std. dev. | Distance added by a typical difference |
|---|---:|---:|
| Cores | 29,869 | 48 → 96: 0.002 |
| Nodes | 622 | 1 → 16: 0.024 |
| Frequency | 98 | 2000 → 2200 MHz: **2.03** |
| Embedding | — | two different job names of one user: median 0.84, p90 1.41, max 1.5 |

So in practice our UoPC means: among the user's newest 500 jobs at the same frequency, take
the 5 with the most similar job name. A handful of enormous jobs inflate the standard
deviations of cores and nodes, so ordinary differences in them barely count. On Eagle and
Kestrel there is no frequency column (it is constant after filling), and the embedding is
ours: harrier-oss-v1-0.6b over partition, qos, account, user, requested walltime, nodes,
cores, GPUs, and the submit weekday and hour.

**Measured (#222 item 4):** the scaling does hold UoPC back. A `balanced` mode scores better
everywhere tried:
- the unpadded reproduction: 9.75% / R² 0.766, against 10.34% / 0.751;
- the rolling F-DATA UoPC: 10.80% / 0.682, against 11.36% / 0.660;
- Eagle and Kestrel, by 0.6 and 1.6 points.

The balanced mode adds log2 nodes and scaled frequency, weighted to about one job-name
distance. On Eagle and Kestrel the z-scored columns are worse than the embedding alone.
R² stays below the paper's 0.80 on its apparent data.

## Deviation 3 — the rolling history cutoff

The benchmark UoPC retrains once per user per day on jobs that ended before the day's split.
Two consequences:
- a job can't use the same user's jobs that finished earlier that day;
- history older than 60 days is dropped.

The reproduction uses everything finished before each job's submission. UoPC gains most from
a user's latest near-identical jobs. **Measured (#222 item 3):** per requested node, the
reproduction scores 8.65% / R² 0.738, against the rolling UoPC's 11.36% / 0.660 on the same
target. So the cutoff costs about 2.7 points, give or take the cold-start fallback and the
slightly different test sets. With `balanced` features and k = 20 (#228) it is 7.82% against
10.29%, about 2.5 points; with the median as well (#241), 7.63% against 10.57%, about 2.9.

The reproduction's 9.93% against 11.36% mixed two effects that partly cancel. Dividing by
requested nodes lowers MAPE (9.93% → 8.65%); the cutoff raises it (8.65% → 11.36%).

Without the padded jobs, the reproduction scores 10.34% / 0.751. That matches the paper's
MAPE, but its R² is below the paper's 0.80, so the padded jobs don't explain the whole R²
difference.

## The authors' code

**UoPC** (`predict.py`, `feature_encoders/`, `predictive_models/KNN.py`):
- It reads one user's dataset and keeps the newest θ rows by a configured `order_by`
  (`end_time` in the example; θ = 50 in the README example).
- It SBert-encodes the configured features (example: `job_name, num_cores, num_nodes,
  frequency`) as a comma-joined string.
- It fits `KNeighborsClassifier(k)` on the target as given and predicts the new job.
- The classifier only accepts integer-valued targets. F-DATA's whole-job `avgpcon` is
  integer, but any per-node value is not, so fitting would fail (checked on a toy example).
  Our rounding to whole watts is needed to use a classifier at all; it isn't copied from the
  authors. Only the paper-comparison recipes still vote ([#241](https://github.com/NatLabRockies/hpc-oda-commons/issues/241)).
- `predict.py` imports `predictive_models.knn`, but the file is `KNN.py`. That works only on
  case-insensitive filesystems.

**online-jpcp** (`t.py`, `online_evaluation.py`, `prediction_algorithm.py`,
`encodings.py`):
- Targets are `int(avgpcon / nnuma)`, and the same for `minpcon` and `maxpcon`. PM100 divides
  by `num_nodes_alloc`.
- F-DATA features: `usr, jnam, cnumr, nnumr, CR-STR-jobenv-req, CR-STR-freq-req`.
- Online split: training is `end_day ∈ [d − α, d)`; testing is submitted on days
  `[d, d + β)`; evaluation starts at the first day + α. Day boundaries come from
  `datetime.fromtimestamp`, so they are in the machine's local time zone.
- **It cannot produce the paper's tables as published:**
  - The local `encodings.py` shadows Python's built-in `encodings` module, so
    `from encodings import int_encoding` raises `ImportError` (reproduced with a toy copy).
  - `PredictionAlgorithm.fit` returns `None`, so `model = model(...).fit(df)` loses the
    model.
  - `_data_preparation` returns `.values` (a NumPy array), while both encoders expect a
    DataFrame (`df.columns`, `df.apply`).
  - Bare `except: continue` blocks hide all three failures.
- **Other defects:**
  - INT encoding is fitted separately on the training and test frames, so codes don't match
    between them.
  - The metrics for β > 1 pool predictions from smaller β, because the lists are not reset.
  - Results are saved as `pred_{α}_{β}pickle` but loaded as `pred_{α}_{β}.pickle`.

## Claims to correct

**Fixed** under #222 item 2. The line numbers below refer to the files as audited.

| Where | Claim | What's true |
|---|---|---|
| `models/uopc/model.py:506` and `docs/benchmarking/power/uopc.md:79` | Global z-scoring is done "as the authors' code does" | It's in neither the paper nor the authors' repositories; it's our adaptation |
| `model.py:679`, `uopc.md:22`, `uopc.md:82` | Rounding to integer classes follows the authors' implementation | The classifier follows their code; the rounding is ours, needed for fractional per-node targets |
| `model.py:436-437` | The `nnuma` division follows "the authors' code" | The UoPC code has no division. The paper text and figures, and the JPCP code, support allocated nodes. |
| `model.py:1` | "per-user kNN regression" | The paper mode uses a classifier |
| `uopc.md:92-95` | The paper's tables are behind the paywall and not recorded | Table I is above |
| `uopc.md:121` | "Our test set is larger than the paper's 'more than 700k jobs'" | The paper says >1.3M jobs and >700 users; ours is 1.59M jobs and 764 users |
| `uopc.md:120` | Agreement with an "unsourced figure in the original contribution (MAPE 10.10%, R² 0.833)" | Still unsourced; compare with Table I instead |
| `docs/benchmarking/power/results.md:90` | F-DATA's job name **and requested CPU frequency** may explain its lower error | On F-DATA the tree models use only `name`, `num_cores_req`, `num_nodes_req`, `requested_seconds` and `user`. `freq_req` is outside the feature allowlist, and `jobenv_req` isn't mapped. Only UoPC uses frequency. |

## Frequency and environment as features for the other models

Both are in the paper's F-DATA feature set and are legitimate submit-time features. They add
little. Measured over all five months, per requested node:

- **CPU frequency** has two values, 2000 and 2200 MHz, whose medians differ by 2.7 W. On its
  own it explains 0.2% of power variance.
- **Environment** is essentially two values (plus one with 3 jobs). On its own it explains
  1.9%.

| Group jobs by user + name + cores + nodes, plus… | Variance left unexplained |
|---|---:|
| nothing | 9.03% |
| frequency | 8.98% |
| environment | 8.81% |
| both | 8.76% |

That is an in-sample upper bound. Eagle and Kestrel have neither column, so neither feature
can explain the F-DATA–NLR gap. Adding them is worth doing only alongside a job-name
ablation rerun.

## A paper-style embedding

**An exact copy of the paper's embedding is not possible from public data:**
- the job names and environments are anonymised;
- the paper is ambiguous about the field order, whether the user is included, and L6 or L12;
- the authors' data export differs from the Zenodo files.

Embedding the anonymised tokens would also create false similarity: `jnam_2111729` and
`jnam_2111730` share most of their word pieces.

**A labelled approximation, "paper-style on public data", needs:**
1. A values-only, comma-separated text format in `hpc-oda embed` with a configurable field
   list. Today there are only `prose` and `kv`, both with labels.
2. Mapping `jobenv_req` in `fdata_fugaku.yml` (then `fdata_fugaku_uopc.yml`), and allowing frequency and environment
   as serialisable fields.
3. Making UoPC's extra numeric columns configurable in both modes, including none, so a run
   can use the embedding alone, as the paper does.
4. Embedding with `sentence-transformers/all-MiniLM-L6-v2` in a separate environment with the
   `embed` extra ([why](../../known-issues.md#note--on-macos-torch-and-xgboost-crash-in-one-process)).
   There are 242,481 distinct strings across the 2.93M jobs. Time a sample first.

Comparing it with the current features and with F-DATA's embedding alone would show how much
the encoding matters. It cannot show a match with the paper. If it does worse, anonymisation
is the likely cause.

## Proposed work

1. **Corrections.** Fix the [claims above](#claims-to-correct), record the paper's Table I and
   baselines in `uopc.md`, and describe the feature adaptation and the scaling's effect.
2. **Reproduction reruns** (~28 min each):
   - without the 48× and 24× padded jobs, to match the paper's apparent data;
   - with per-requested-node targets, to separate the node-count effect from the
     history-cutoff effect.
3. **Encoding experiment** on the reproduction and the rolling UoPC:
   - current features;
   - F-DATA's embedding alone;
   - balanced scaling: log cores and nodes, frequency as 0/1;
   - the paper-style embedding above.
4. **Optional:** an F-DATA rerun of the tree models without the job name, and with frequency
   and environment added, to test what explains the F-DATA–NLR gap.

## How the measurements were made

All figures come from the five Zenodo F-DATA monthly files (`23_12` … `24_04`, 2,930,414
rows) or the prepared `fdata_fugaku_uopc` table (since #249, the Dec 2023–Apr 2024 window of `fdata_fugaku`):

- **Test period** is `adt >= 2024-02-01`, 1,598,494 jobs in the raw files, 1,591,115 of
  them usable (with both targets, an embedding and a node count).
- **The paper's figures** were rendered at 300 dpi from the PDF and read by eye.
- **The authors' repositories** were read, not run. The three failures were reproduced with
  toy files written for the purpose.

## Appendix: the #222 measurements

Moved here from [uopc.md](uopc.md), which keeps a summary of each. They ran with k = 5 and the
vote, the defaults until #228 and #241.

### Z-scored features: the numbers

On F-DATA, one embedding is at most 1.5 from another, with a median of 0.84 between two job
names of one user. Against that:

- Frequency has two values, so its z-scores are at least 2 apart (2.03 here) whatever
  the data. A frequency mismatch therefore outweighs any difference in job name.
- A few enormous jobs inflate the spread of cores (std. dev. 29,869) and nodes (622).
  So ordinary differences barely count: 48 → 96 cores adds 0.002, and 1 → 16 nodes
  0.024.
- In practice the neighbours are the user's jobs at the same frequency with the most
  similar job names.

### The θ × k sweep on the authors' setup

The first sweep ran per allocated node with `zscore` features, at 76f4f0f, and is kept for
the comparison with the paper. Like the paper's, it put θ = 500, k = 5 close to the best. The
full grid took 2 h 15 min (7 to 51 minutes per θ, the most at θ = 5000) and peaked at ~17 GB
resident. Each cell shows MAPE / R² on average power per allocated node; coverage is as in
[uopc.md's sweep](uopc.md#sensitivity-sweep-θ--k).

**Classifier** (the paper's predictor, a majority vote over rounded watts):

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 19.49% / 0.769 | 15.92% / 0.771 | 14.74% / 0.769 | 15.09% / 0.751 |
| 100 | 15.39% / 0.800 | 19.32% / 0.790 | 14.03% / 0.780 | 14.07% / 0.771 |
| 200 | 11.12% / 0.824 | 13.76% / 0.817 | 19.14% / 0.803 | 13.60% / 0.783 |
| 500 | 9.65% / 0.840 | 9.56% / 0.848 | 10.74% / 0.841 | 18.92% / 0.812 |
| 1000 | 9.56% / 0.841 | 9.40% / 0.850 | 9.71% / 0.849 | 13.30% / 0.823 |
| 2000 | 9.60% / 0.837 | 9.32% / 0.848 | 9.49% / 0.847 | 10.17% / 0.842 |
| 5000 | 10.01% / 0.816 | 9.68% / 0.829 | 9.81% / 0.826 | 10.27% / 0.824 |

**Regressor** (the mean of the same neighbours, an ablation):

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 27.65% / 0.806 | 33.24% / 0.805 | 39.34% / 0.800 | 54.75% / 0.788 |
| 100 | 17.36% / 0.832 | 26.06% / 0.826 | 30.93% / 0.819 | 37.57% / 0.810 |
| 200 | 11.21% / 0.851 | 14.62% / 0.849 | 25.02% / 0.840 | 32.57% / 0.828 |
| 500 | 9.15% / 0.870 | 9.70% / 0.872 | 12.24% / 0.868 | 24.43% / 0.852 |
| 1000 | 9.04% / 0.871 | 9.13% / 0.875 | 9.79% / 0.876 | 13.70% / 0.867 |
| 2000 | 9.06% / 0.873 | 9.02% / 0.878 | 9.22% / 0.881 | 10.62% / 0.880 |
| 5000 | 9.50% / 0.859 | 9.40% / 0.865 | 9.57% / 0.867 | 10.21% / 0.865 |

<details>
<summary>Peak power (maxpcon per allocated node)</summary>

Classifier:

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 19.21% / 0.769 | 15.97% / 0.765 | 14.79% / 0.767 | 15.50% / 0.741 |
| 100 | 15.52% / 0.790 | 18.48% / 0.782 | 14.14% / 0.778 | 14.25% / 0.768 |
| 200 | 11.30% / 0.816 | 13.52% / 0.808 | 18.50% / 0.795 | 13.82% / 0.776 |
| 500 | 9.85% / 0.831 | 9.86% / 0.835 | 10.89% / 0.830 | 18.60% / 0.804 |
| 1000 | 9.89% / 0.830 | 9.80% / 0.835 | 9.89% / 0.836 | 12.89% / 0.816 |
| 2000 | 9.78% / 0.829 | 9.72% / 0.834 | 9.75% / 0.833 | 10.30% / 0.832 |
| 5000 | 10.21% / 0.805 | 9.79% / 0.816 | 9.83% / 0.814 | 10.32% / 0.810 |

Regressor:

| θ \ k | 5 | 10 | 20 | 50 |
|---|---:|---:|---:|---:|
| 50 | 28.18% / 0.799 | 34.04% / 0.797 | 40.46% / 0.793 | 55.94% / 0.783 |
| 100 | 17.74% / 0.823 | 26.57% / 0.817 | 31.64% / 0.813 | 38.62% / 0.805 |
| 200 | 11.57% / 0.840 | 15.02% / 0.838 | 25.57% / 0.831 | 33.42% / 0.820 |
| 500 | 9.50% / 0.858 | 10.07% / 0.860 | 12.61% / 0.857 | 24.97% / 0.844 |
| 1000 | 9.45% / 0.860 | 9.54% / 0.863 | 10.20% / 0.865 | 14.09% / 0.858 |
| 2000 | 9.43% / 0.862 | 9.40% / 0.867 | 9.59% / 0.871 | 10.98% / 0.871 |
| 5000 | 9.71% / 0.849 | 9.59% / 0.856 | 9.76% / 0.857 | 10.40% / 0.855 |

</details>

What that grid showed:

- **θ matters more than k.** MAPE falls from 15–19% at θ = 50 to 9.3–10.7% for
  θ = 500–2000 with k ≤ 20. θ = 5000 is slightly worse on every metric: the oldest history hurts more
  than it helps.
- **The paper's θ = 500, k = 5 is close to the best.** The best classifier cell is θ = 2000,
  k = 10 (9.32%, R² 0.848), 0.3 points better.
- **Voting on rounded watts costs R².** The mean of the same neighbours has the higher R²
  in every cell (0.79–0.88 against 0.75–0.85). Its MAPE is lower only with a large θ and
  small k; the best cell overall is the regressor at θ = 2000, k = 10 (9.02%, R² 0.878).
  Elsewhere the regressor's MAPE rises quickly with k, because averaging in one normal job
  ruins a 1.9 W target ([padded allocations](uopc.md#nodes-requested-not-allocated)).
- **The classifier spikes at k = θ/10**: 19.5% at (50, 5), 19.3% at (100, 10), 19.1% at
  (200, 20) and 18.9% at (500, 50), with R² smooth across those cells. Re-running the sweep's
  own neighbour search and vote on samples of 20,000 test jobs at θ = 100 puts the whole
  spike on the padded users. Their MAPE is 41% at k = 5, 75% at k = 10 and 26% at k = 20.
  A sample of 120 other users stays at 12.8–13.4% for every k. Why those sizes in
  particular is not established; it comes from the vote over these users' mix of ~2 W and
  normal targets, and does not affect the other users.
- **The headline cell differs from the reproduction run** (9.65% against 9.93% MAPE at
  θ = 500, k = 5) because of exact ties. Many jobs have identical features: in the
  samples above, 30% of queries had all 50 nearest neighbours at distance 0. The sweep takes
  the first k of its 50 nearest neighbours, while the reproduction asks scikit-learn for k
  directly, and the two pick different jobs among equally near ones. Both are valid
  readings of the protocol; the spread between them, ~0.3 points, is the tolerance to
  compare within.

### Feature modes, measured

Each run below is a bundled recipe plus one `uopc_features` key. The variant recipes are not
bundled. They ran on 2026-10-19 at 935e58a, and the `zscore` rows are the earlier results.
Every run in this section uses k = 5, the default until #228, and the vote, the default until
#241; our results at k = 20 with the median are in
[Our reproduction](uopc.md#our-reproduction-θ--500-k--20) and the [power results](results.md).

**Unpadded reproduction** (`uopc_paper_reproduction_unpadded.yml`, the paper's apparent data):

| Target | Features | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| Average | Paper (Table I) | | | 10% | 0.80 |
| | `zscore` | 7.07 | 17.01 | 10.34% | 0.751 |
| | `embedding` | 7.83 | 18.31 | 11.62% | 0.711 |
| | **`balanced`** | **6.78** | **16.48** | **9.75%** | **0.766** |
| Peak | Paper (Table I) | | | 10% | 0.79 |
| | `zscore` | 7.41 | 18.62 | 10.54% | 0.737 |
| | `embedding` | 8.26 | 19.97 | 11.93% | 0.697 |
| | **`balanced`** | **7.09** | **18.02** | **9.93%** | **0.753** |

**Per requested node, all jobs** (`uopc_paper_reproduction.yml` at k = 5; the `balanced`
rows ran at 8d914e7):

| Target | Features | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| Average | `zscore` | 6.30 | 15.97 | 8.65% | 0.738 |
| | **`balanced`** | **6.11** | **15.50** | **8.29%** | **0.753** |
| Peak | `zscore` | 6.67 | 17.56 | 8.91% | 0.718 |
| | **`balanced`** | **6.39** | **16.94** | **8.47%** | **0.737** |

**Rolling benchmark UoPC** (`uopc_rolling_*.yml`, [power results](results.md)):

| Data | Features | MAE | RMSE | MAPE | R² |
|---|---|---:|---:|---:|---:|
| F-DATA, average | `zscore` | 8.01 | 18.13 | 11.36% | 0.660 |
| | `embedding` | 8.41 | 18.78 | 11.86% | 0.635 |
| | **`balanced`** | **7.71** | **17.55** | **10.80%** | **0.682** |
| F-DATA, peak | `zscore` | 8.60 | 20.04 | 11.73% | 0.629 |
| | `embedding` | 9.05 | 20.81 | 12.29% | 0.600 |
| | **`balanced`** | **8.27** | **19.44** | **11.15%** | **0.651** |
| Eagle, average | `zscore` | 80.94 | 116.87 | 24.15% | −0.141 |
| | `embedding` | 79.02 | 113.94 | 23.66% | −0.084 |
| | **`balanced`** | **78.59** | **113.43** | **23.54%** | **−0.075** |
| Kestrel, average | `zscore` | 125.34 | 190.91 | 26.27% | −0.157 |
| | `embedding` | 114.56 | 179.12 | 24.74% | −0.018 |
| | **`balanced`** | **114.37** | **178.84** | **24.69%** | **−0.015** |

What they show:

- **`balanced` is best everywhere tried.**
  - On F-DATA it gains 0.4–0.6 MAPE points and about 0.02 R² over `zscore`, in both
    protocols, on both targets and with either node count.
  - The unpadded reproduction drops below the paper's 10% MAPE.
  - The rolling UoPC reaches 10.80%, between XGBoost (11.05%) and MoE XGBoost (10.07%) on
    average power. Its R² of 0.682 is still well below theirs (0.81 and 0.78).
- **On F-DATA the numbers carry real information.** `embedding` alone is worst there,
  because F-DATA's embedding holds only user, job name and environment. So `zscore` was using the numbers
  badly, not using numbers it shouldn't.
- **On Eagle and Kestrel, `zscore` actively hurts.**
  - `embedding` alone beats it by 0.5 and 1.5 points.
  - Our embedding there already includes the requested nodes in its text, so the z-scored
    columns add distortion rather than information.
  - `balanced` is level with `embedding`.
  - UoPC stays far behind the tree models on both systems either way (R² below zero, ~24%
    against ~20%).
- **The balanced weights were set for F-DATA's embedding.** On Eagle and Kestrel our harrier
  embedding sits much closer: the median within-user distance is ~0.2, against 0.84. One
  doubling of nodes there weighs about as much as a typical job-name difference, roughly
  four times its relative weight on F-DATA.
