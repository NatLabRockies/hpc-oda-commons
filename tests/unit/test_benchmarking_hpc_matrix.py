"""Unit tests for the HPC benchmark-matrix runner (config, planning, slicing)."""

from __future__ import annotations

import datetime
import json
from dataclasses import replace
from pathlib import Path

import pyarrow as pa
import pytest

from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.benchmarking.hpc.config import SiteConfigError, load_site_config
from hpc_oda_commons.benchmarking.hpc.matrix import (
    EMBEDDING_MODEL,
    MAX_NODE_ROWS,
    MODEL_SPLIT_OVERRIDES,
    RUNTIME_MODELS,
    SPLIT,
    TIERS,
    Card,
    ModelSelectionError,
    build_plan,
    build_recipe,
    load_cards,
    render_template,
    select_models,
    slice_extension_for,
    tier_for_rows,
    write_plan,
)
from hpc_oda_commons.benchmarking.hpc.slice import (
    SliceError,
    effective_start,
    slice_dataset,
    slice_to_window,
)

_UTC = datetime.timezone.utc

_VALID_SITE = """\
schema_version: oda.hpc_site.v0.1.0
host: mycluster
user: someone
account: proj123
remote_base: /scratch/bench
env_prefix: /scratch/bench/env
conda_module: anaconda3
gpu_gres: "gpu:a100:1"
partitions:
  cpu: standard
  bigmem: bigmem
  gpu: gpu
embedding_model: stub
"""


def _write_site(tmp_path: Path, text: str = _VALID_SITE) -> Path:
    p = tmp_path / "hpc-site.yml"
    p.write_text(text, encoding="utf-8")
    return p


# --- config -------------------------------------------------------------------------


def test_load_site_config_resolves_paths_and_defaults(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    assert cfg.host == "mycluster"
    assert cfg.account == "proj123"
    assert cfg.repo_dir == "/scratch/bench/hpc-oda-commons"
    assert cfg.hpc_oda == "/scratch/bench/env/bin/hpc-oda"
    assert cfg.cache_dir == "/scratch/bench/cache"
    assert cfg.hf_home == "/scratch/bench/hf"
    assert cfg.partition("bigmem") == "bigmem"


def test_load_site_config_missing_file_points_to_example(tmp_path: Path) -> None:
    with pytest.raises(SiteConfigError, match="site.example.yml"):
        load_site_config(tmp_path / "nope.yml")


def test_load_site_config_rejects_placeholders(tmp_path: Path) -> None:
    text = _VALID_SITE.replace("host: mycluster", "host: your-ssh-alias")
    with pytest.raises(SiteConfigError, match="placeholder"):
        load_site_config(_write_site(tmp_path, text))


def test_load_site_config_requires_the_partitions_it_schedules_on(tmp_path: Path) -> None:
    text = _VALID_SITE.replace("  cpu: standard\n", "")
    with pytest.raises(SiteConfigError, match="cpu"):
        load_site_config(_write_site(tmp_path, text))


def test_bigmem_is_not_a_required_partition(tmp_path: Path) -> None:
    """Nothing is scheduled there any more, so a site must not be made to name one."""
    text = _VALID_SITE.replace("  bigmem: bigmem\n", "")

    cfg = load_site_config(_write_site(tmp_path, text))

    assert cfg.partition("cpu") == "standard"


# --- tiers --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        (0, "light"),
        (299_999, "light"),
        (300_000, "heavy"),
        (1_999_999, "heavy"),
        (2_000_000, "extreme"),
    ],
)
def test_tier_for_rows_boundaries(rows: int, expected: str) -> None:
    assert tier_for_rows(rows).name == expected


# --- planning -----------------------------------------------------------------------


def _card(name: str, rows: int, healthy: bool = True, train_days: int = 60) -> Card:
    return Card(
        dataset=name,
        window_rows=rows,
        window_start="2025-01-01",
        window_end="2025-03-31",
        train_days=train_days,
        healthy=healthy,
        system=name,
        source_table=f"data/datasets/{name}/data.parquet",
        card_path=Path(f"{name}.card.json"),
    )


def test_build_plan_cell_and_embed_counts(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    cards = [_card("small", 1000), _card("big", 5_000_000)]
    plan = build_plan(cards, cfg, plan_id="p1")

    assert len(plan.cells) == 2 * len(RUNTIME_MODELS)
    assert len(plan.embeds) == 2  # one embed job per dataset
    big_cells = [c for c in plan.cells if c.dataset == "big"]
    # Even the extreme tier runs on the ordinary CPU partition now.
    assert {c.partition for c in big_cells} == {"standard"}


def test_build_plan_embedding_cells_read_embedded_parquet(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    plan = build_plan([_card("ds", 1000)], cfg, plan_id="p1")
    emb = [c for c in plan.cells if c.model == EMBEDDING_MODEL.removeprefix("job_runtime_")]
    other = [c for c in plan.cells if c not in emb]
    assert all(c.needs_embed and "embeddings" in c.table_path for c in emb)
    assert all(not c.needs_embed and "windows" in c.table_path for c in other)


def test_build_plan_skips_unhealthy_unless_forced(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    cards = [_card("ok", 1000), _card("bad", 1000, healthy=False)]

    plan = build_plan(cards, cfg, plan_id="p1")
    assert {c.dataset for c in plan.cells} == {"ok"}
    assert len(plan.skipped) == 1 and plan.skipped[0]["dataset"] == "bad"

    forced = build_plan(cards, cfg, plan_id="p1", include_unhealthy=True)
    assert {c.dataset for c in forced.cells} == {"ok", "bad"}
    assert forced.skipped == []


def test_write_plan_emits_valid_recipes_and_filled_scripts(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    plan = build_plan([_card("ds", 1000)], cfg, plan_id="p1")
    staging = tmp_path / "staging"
    plan_path = write_plan(plan, staging, cfg)

    # every recipe validates against the recipe schema
    recipes = sorted(staging.glob("recipes/*.yml"))
    assert len(recipes) == len(RUNTIME_MODELS)
    for r in recipes:
        load_recipe(r, validate=True)

    # scripts have no unfilled template placeholders and charge the right account
    for s in sorted(staging.glob("scripts/*.sbatch")):
        text = s.read_text(encoding="utf-8")
        assert "{{" not in text
        assert "--account=proj123" in text

    # the embed script loads the model from the shared cache offline
    embed_script = (staging / "scripts" / "embed__ds.sbatch").read_text(encoding="utf-8")
    assert "export HF_HOME=/scratch/bench/hf" in embed_script
    assert "export HF_HUB_OFFLINE=1" in embed_script
    assert "#SBATCH --mem=64G" in embed_script  # light tier embed memory (was unset → OOM)

    plan_json = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_json["n_cells"] == len(RUNTIME_MODELS)
    assert plan_json["n_embeds"] == 1


def test_window_parallel_cells_get_the_tier_worker_count(tmp_path: Path) -> None:
    import yaml

    cfg = load_site_config(_write_site(tmp_path))
    # light tier and extreme tier, so window_n_jobs must track the tier's worker budget.
    plan = build_plan([_card("small", 1000), _card("big", 5_000_000)], cfg, plan_id="p1")
    staging = tmp_path / "staging"
    write_plan(plan, staging, cfg)

    def _split(dataset: str, tag: str) -> dict:
        payload = yaml.safe_load(
            (staging / "recipes" / f"{dataset}__{tag}.yml").read_text(encoding="utf-8")
        )
        return payload["split"]

    light, extreme = TIERS[0].window_workers, TIERS[2].window_workers
    # Workers are a memory budget, so the bigger tier gets *fewer*, not more.
    assert extreme < light
    for tag in ("mlp", "tfidf_knn", "moe_xgboost"):
        assert _split("small", tag)["window_n_jobs"] == light
        assert _split("big", tag)["window_n_jobs"] == extreme
    # RF/XGBoost run windows sequentially (RF already parallelizes inside each fit).
    assert "window_n_jobs" not in _split("small", "xgboost")
    assert "window_n_jobs" not in _split("big", "random_forest")


# --- node-sized cells (#145) --------------------------------------------------------


def test_cells_are_sized_from_the_slice_they_load_not_the_card(tmp_path: Path) -> None:
    """The card window and the slice on disk diverge by the lookback extension.

    Sizing from the card would under-provision every cell by that width -- e.g. a dataset
    whose card says 1.6M rows but whose slice holds 2.4M.
    """
    cfg = load_site_config(_write_site(tmp_path))
    card = _card("ds", 1_000)  # card says "light"
    card = replace(card, sliced_rows=5_000_000)  # the slice on disk says otherwise

    plan = build_plan([card], cfg, plan_id="p1")

    assert {c.tier for c in plan.cells} == {"extreme"}


def test_load_cards_reads_the_slice_sidecar(tmp_path: Path) -> None:
    cards_dir, windows_dir = tmp_path / "cards", tmp_path / "windows"
    cards_dir.mkdir()
    (cards_dir / "ds.card.json").write_text(
        json.dumps(
            {
                "benchmark_window": {
                    "n_rows": 100,
                    "window_start": "2025-03-29",
                    "window_end": "2025-06-26",
                    "healthy": True,
                    "rule": {"train_days": 60, "test_days": 30},
                },
                "source": {"system": "ds", "table_path": "data/datasets/ds/data.parquet"},
            }
        ),
        encoding="utf-8",
    )
    (windows_dir / "ds").mkdir(parents=True)
    (windows_dir / "ds" / "slice.json").write_text(json.dumps({"rows": 4242}), encoding="utf-8")

    (with_slice,) = load_cards(cards_dir, windows_dir)
    (without,) = load_cards(cards_dir)

    assert with_slice.sliced_rows == 4242
    assert with_slice.effective_rows == 4242
    # No sidecar: fall back to the card rather than failing.
    assert without.sliced_rows is None
    assert without.effective_rows == 100


def test_a_slice_too_big_for_one_node_is_skipped_with_a_reason(tmp_path: Path) -> None:
    """Big-memory nodes are not used, so an outsized dataset is reported, not relocated."""
    cfg = load_site_config(_write_site(tmp_path))
    card = replace(_card("huge", 1_000), sliced_rows=MAX_NODE_ROWS + 1)

    plan = build_plan([card, _card("ok", 1_000)], cfg, plan_id="p1")

    assert {c.dataset for c in plan.cells} == {"ok"}
    (skipped,) = plan.skipped
    assert skipped["dataset"] == "huge"
    assert "exceeds what one node can hold" in skipped["reason"]


def test_no_cell_is_scheduled_on_a_big_memory_partition(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    cards = [_card("a", 1_000), _card("b", 1_000_000), _card("c", 5_000_000)]

    plan = build_plan(cards, cfg, plan_id="p1")

    assert {t.partition_kind for t in TIERS} == {"cpu"}
    assert {c.partition for c in plan.cells} == {"standard"}


def test_every_script_ignores_the_submitting_user_site_packages(tmp_path: Path) -> None:
    """The env is the only source of truth for imports, whoever types sbatch (#155).

    Without this, a package present in one user's ~/.local shadows the env's copy, so the
    same plan runs different library versions per submitter -- and a package missing from
    the shared env fails only for whoever lacks a home copy.
    """
    cfg = load_site_config(_write_site(tmp_path))
    plan = build_plan([_card("ds", 1000)], cfg, plan_id="p1")
    staging = tmp_path / "staging"
    write_plan(plan, staging, cfg)

    scripts = sorted(staging.glob("scripts/*.sbatch"))
    assert scripts  # guard: an empty glob would pass the loop vacuously
    for script in scripts:
        assert "export PYTHONNOUSERSITE=1" in script.read_text(encoding="utf-8"), script.name


def test_bench_script_takes_the_whole_node_and_reads_its_core_count(tmp_path: Path) -> None:
    """Cores are free under an exclusive partition; a baked-in count only wastes them."""
    cfg = load_site_config(_write_site(tmp_path))
    plan = build_plan([_card("ds", 1000)], cfg, plan_id="p1")
    staging = tmp_path / "staging"
    write_plan(plan, staging, cfg)

    script = (staging / plan.cells[0].script_path).read_text(encoding="utf-8")

    assert "--exclusive" in script
    assert "--cpus-per-task" not in script
    assert "OMP_NUM_THREADS=${SLURM_CPUS_ON_NODE:-1}" in script


# --- per-model split overrides (#145) -----------------------------------------------


def _split_of(model_key: str) -> dict:
    return build_recipe("ds", model_key, "data/windows/ds/data.parquet", "runs/ds")["split"]


def test_both_xgboost_variants_fit_absolute_error() -> None:
    """If only the MoE fitted absolute error, its margin would bundle an objective effect.

    The leaderboard's headline comparison is MoE vs plain XGBoost; that has to be about
    routing and recency, not about which loss the trees were fitted to (#138, #145).
    """
    assert _split_of("job_runtime_xgboost")["objective"] == "reg:absoluteerror"
    assert _split_of("job_runtime_moe_xgboost")["objective"] == "reg:absoluteerror"


def test_moe_cells_carry_the_best_measured_routing() -> None:
    split = _split_of("job_runtime_moe_xgboost")

    assert split["enable_power_users"] is False
    assert split["time_decay_rate"] == 0.05


def test_models_without_overrides_keep_the_shared_split() -> None:
    """An override must not leak into models that were never measured with it."""
    for model_key in ("job_runtime_baseline", "job_runtime_mlp", "job_runtime_random_forest"):
        assert _split_of(model_key) == dict(SPLIT)


def test_overrides_do_not_mutate_the_shared_split() -> None:
    """``build_recipe`` copies before layering; a leak here would poison later cells."""
    _split_of("job_runtime_moe_xgboost")

    assert "objective" not in SPLIT
    assert "enable_power_users" not in SPLIT


def test_every_overridden_model_is_actually_in_the_fleet() -> None:
    """An override for a model the planner never emits is dead configuration."""
    assert set(MODEL_SPLIT_OVERRIDES) <= set(RUNTIME_MODELS)


def test_moe_is_in_the_fleet(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    plan = build_plan([_card("small", 1000)], cfg, plan_id="p1")

    assert "job_runtime_moe_xgboost" in RUNTIME_MODELS
    assert "moe_xgboost" in {cell.model for cell in plan.cells}


# --- derived slice extension (#145) -------------------------------------------------


def test_slice_extension_covers_the_split_shortfall() -> None:
    """The split asks for more history than the card window holds; the slice makes it up."""
    lookback = int(SPLIT["training_lookback_days"])

    assert slice_extension_for(_card("d", 10, train_days=60)) == lookback - 60
    # A card already wider than the split needs no extension -- and must not get a negative one.
    assert slice_extension_for(_card("d", 10, train_days=lookback + 30)) == 0


def test_slice_extension_for_a_card_with_no_stated_rule() -> None:
    """Unknown ``train_days`` extends by the full lookback: wider than needed, never narrower."""
    assert slice_extension_for(_card("d", 10, train_days=0)) == int(SPLIT["training_lookback_days"])


def test_card_carries_the_window_rule_train_days(tmp_path: Path) -> None:
    (tmp_path / "ds.card.json").write_text(
        json.dumps(
            {
                "benchmark_window": {
                    "n_rows": 100,
                    "window_start": "2025-03-29",
                    "window_end": "2025-06-26",
                    "healthy": True,
                    "rule": {"anchor": 0.8, "train_days": 60, "test_days": 30},
                },
                "source": {"system": "ds", "table_path": "data/datasets/ds/data.parquet"},
            }
        ),
        encoding="utf-8",
    )

    (card,) = load_cards(tmp_path)

    assert card.train_days == 60


# --- template rendering -------------------------------------------------------------


def test_render_template_fills_and_flags_unfilled() -> None:
    assert render_template("a={{x}} b={{y}}", {"x": 1, "y": "z"}) == "a=1 b=z"
    with pytest.raises(KeyError, match="unknown keys"):
        render_template("{{missing}}", {"x": 1})


# --- slicing (overlap predicate) ----------------------------------------------------


def _job_table() -> pa.Table:
    # (submit, end) intervals, in days from 2025-01-01
    rows = [
        ("in_window", 5, 6),  # fully inside
        ("test_row", 70, 71),  # inside test region
        ("long_pre_window", -3, 2),  # submitted before window, ends inside → training row, KEEP
        ("before_window", -10, -8),  # entirely before → drop
        ("after_window", 95, 96),  # submitted after window end → drop
    ]
    base = datetime.datetime(2025, 1, 1, tzinfo=_UTC)
    submit = [base + datetime.timedelta(days=s) for _, s, _ in rows]
    end = [base + datetime.timedelta(days=e) for _, _, e in rows]
    return pa.table(
        {
            "job_id": pa.array([r[0] for r in rows]),
            "submit_time": pa.array(submit, type=pa.timestamp("us", tz="UTC")),
            "end_time": pa.array(end, type=pa.timestamp("us", tz="UTC")),
            "runtime_seconds": pa.array([86400.0] * len(rows)),
        }
    )


def test_slice_keeps_interval_overlap_including_long_pre_window_jobs() -> None:
    sliced = slice_to_window(_job_table(), "2025-01-01", "2025-03-31")
    kept = set(sliced.column("job_id").to_pylist())
    assert kept == {"in_window", "test_row", "long_pre_window"}
    assert "before_window" not in kept
    assert "after_window" not in kept


def test_slice_dataset_roundtrips_parquet(tmp_path: Path) -> None:
    import pyarrow.parquet as pq

    src = tmp_path / "canonical.parquet"
    pq.write_table(_job_table(), src)
    out = tmp_path / "windows" / "ds" / "data.parquet"
    n = slice_dataset(src, out, "2025-01-01", "2025-03-31")
    assert n == 3
    assert out.exists()
    assert pq.read_table(out).num_rows == 3


def test_extra_lookback_extends_only_the_lower_bound() -> None:
    """More training history, same test region — the point of the option (#143)."""
    table = _job_table()

    plain = set(slice_to_window(table, "2025-01-01", "2025-03-31").column("job_id").to_pylist())
    extended = set(
        slice_to_window(table, "2025-01-01", "2025-03-31", extra_lookback_days=10)
        .column("job_id")
        .to_pylist()
    )

    # A job entirely before the card window becomes a legitimate training row...
    assert "before_window" not in plain
    assert "before_window" in extended
    # ...and nothing new arrives at the top end.
    assert "after_window" not in extended
    assert extended - plain == {"before_window"}


def test_effective_start_moves_back_by_whole_days() -> None:
    assert effective_start("2025-03-29") == "2025-03-29"
    # The extension this repo's reference recipe uses: card window minus 60 days.
    assert effective_start("2025-03-29", 60) == "2025-01-28"
    with pytest.raises(SliceError, match="must be >= 0"):
        effective_start("2025-03-29", -1)


def test_slice_dataset_records_which_window_it_wrote(tmp_path: Path) -> None:
    """A windowed parquet is path-identical whatever window it holds; the sidecar says."""
    import json

    import pyarrow.parquet as pq

    src = tmp_path / "canonical.parquet"
    pq.write_table(_job_table(), src)
    out = tmp_path / "windows" / "ds" / "data.parquet"

    n = slice_dataset(src, out, "2025-01-01", "2025-03-31", extra_lookback_days=10)

    provenance = json.loads((out.parent / "slice.json").read_text(encoding="utf-8"))
    assert provenance["card_window"] == {"start": "2025-01-01", "end": "2025-03-31"}
    assert provenance["effective_window"] == {"start": "2024-12-22", "end": "2025-03-31"}
    assert provenance["extra_lookback_days"] == 10
    assert provenance["rows"] == n == 4


# --- model selection (#156) ---------------------------------------------------------


def test_no_exclusions_plans_the_whole_roster() -> None:
    assert select_models() == RUNTIME_MODELS


def test_a_model_can_be_excluded_by_key_or_by_tag() -> None:
    """Both spellings appear in the tooling -- plan output uses tags, the roster uses keys."""
    assert select_models(["job_runtime_mlp"]) == select_models(["mlp"])
    assert "job_runtime_mlp" not in select_models(["mlp"])


def test_exclusion_preserves_roster_order_and_drops_only_what_was_named() -> None:
    kept = select_models(["mlp", "job_runtime_baseline"])

    assert kept == tuple(
        m for m in RUNTIME_MODELS if m not in {"job_runtime_mlp", "job_runtime_baseline"}
    )


def test_an_unknown_exclusion_is_an_error_not_a_silent_no_op() -> None:
    """A typo that quietly planned the full matrix is the surprise this option prevents."""
    with pytest.raises(ModelSelectionError, match="job_runtime_mpl"):
        select_models(["job_runtime_mpl"])


def test_excluding_everything_is_an_error() -> None:
    with pytest.raises(ModelSelectionError, match="nothing left to plan"):
        select_models(list(RUNTIME_MODELS))


def test_excluding_the_embedding_model_drops_the_embed_jobs(tmp_path: Path) -> None:
    """Nothing but ``embedding_knn`` consumes an embedded parquet, so the GPU pass is moot."""
    cfg = load_site_config(_write_site(tmp_path))
    models = select_models(["embedding_knn"])

    plan = build_plan([_card("ds", 1000)], cfg, plan_id="p1", models=models)

    assert plan.embeds == []
    assert not any(c.needs_embed for c in plan.cells)


def test_an_excluded_model_gets_no_cells_recipes_or_scripts(tmp_path: Path) -> None:
    cfg = load_site_config(_write_site(tmp_path))
    plan = build_plan([_card("ds", 1000)], cfg, plan_id="p1", models=select_models(["mlp"]))
    staging = tmp_path / "staging"
    write_plan(plan, staging, cfg)

    assert len(plan.cells) == len(RUNTIME_MODELS) - 1
    assert "mlp" not in {c.model for c in plan.cells}
    assert not list(staging.glob("recipes/*__mlp.yml"))
    assert not list(staging.glob("scripts/*__mlp.sbatch"))
