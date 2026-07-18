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
    RUNTIME_MODELS,
    Card,
    build_plan,
    render_template,
    tier_for_rows,
    write_plan,
)
from hpc_oda_commons.benchmarking.hpc.slice import slice_dataset, slice_to_window

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


def _card(name: str, rows: int, healthy: bool = True) -> Card:
    return Card(
        dataset=name,
        window_rows=rows,
        window_start="2025-01-01",
        window_end="2025-03-31",
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

    plan_json = json.loads(plan_path.read_text(encoding="utf-8"))
    assert plan_json["n_cells"] == len(RUNTIME_MODELS)
    assert plan_json["n_embeds"] == 1


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
