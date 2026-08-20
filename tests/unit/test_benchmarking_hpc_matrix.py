"""Unit tests for the HPC benchmark-matrix runner (config, planning, slicing)."""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pyarrow as pa
import pytest

from hpc_oda_commons.benchmark.recipes import load_recipe
from hpc_oda_commons.benchmarking.hpc.config import SiteConfigError, load_site_config
from hpc_oda_commons.benchmarking.hpc.matrix import (
    EMBEDDING_MODEL,
    MODEL_SPLIT_OVERRIDES,
    RUNTIME_MODELS,
    SPLIT,
    Card,
    build_plan,
    build_recipe,
    load_cards,
    render_template,
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


def test_load_site_config_requires_all_partitions(tmp_path: Path) -> None:
    text = _VALID_SITE.replace("  bigmem: bigmem\n", "")
    with pytest.raises(SiteConfigError, match="bigmem"):
        load_site_config(_write_site(tmp_path, text))


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
    assert {c.partition for c in big_cells} == {"bigmem"}  # extreme tier → bigmem


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


def test_mlp_cells_run_windows_across_allocated_cores(tmp_path: Path) -> None:
    import yaml

    cfg = load_site_config(_write_site(tmp_path))
    # light tier (16 cpus) and extreme tier (64 cpus) so window_n_jobs must track cpus.
    plan = build_plan([_card("small", 1000), _card("big", 5_000_000)], cfg, plan_id="p1")
    staging = tmp_path / "staging"
    write_plan(plan, staging, cfg)

    def _split(dataset: str, tag: str) -> dict:
        payload = yaml.safe_load(
            (staging / "recipes" / f"{dataset}__{tag}.yml").read_text(encoding="utf-8")
        )
        return payload["split"]

    # MLP and TF-IDF kNN spread their independent per-window fits over the cell's cores.
    assert _split("small", "mlp")["window_n_jobs"] == 16  # light tier
    assert _split("big", "mlp")["window_n_jobs"] == 64  # extreme tier
    assert _split("small", "tfidf_knn")["window_n_jobs"] == 16  # light tier
    assert _split("big", "tfidf_knn")["window_n_jobs"] == 64  # extreme tier
    # RF/XGBoost run windows sequentially (RF already parallelizes inside each fit).
    assert "window_n_jobs" not in _split("small", "xgboost")
    assert "window_n_jobs" not in _split("big", "random_forest")


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
