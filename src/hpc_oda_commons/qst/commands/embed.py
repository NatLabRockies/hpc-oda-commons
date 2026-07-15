"""CLI: ``hpc-oda embed`` — serialize an ingested job table and embed each row.

Produces an embedded parquet (original columns + a dense ``embedding`` column) plus a
provenance manifest, for use by ``model.job_runtime_embedding_knn``. The embedding
model is swappable; ``--model stub`` uses a deterministic dependency-free encoder for
offline/CI. Extra text columns (e.g. local job scripts) are configured only via a local
``--config`` file so sensitive content never lands on the command line or in the repo.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
import yaml
from rich.console import Console

from hpc_oda_commons.embeddings.encoders import build_encoder
from hpc_oda_commons.embeddings.serialize import EmbedConfig, LeakageError

console = Console()


def _load_config(config_path: Path | None, text_format: str, instruction: str) -> EmbedConfig:
    data: dict = {}
    if config_path is not None:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise typer.BadParameter(f"config {config_path} must be a YAML mapping")
        data = loaded
    try:
        return EmbedConfig(
            text_format=str(data.get("text_format", text_format)),
            format_version=str(data.get("format_version", "v1")),
            submit_time_field=str(data.get("submit_time_field", "submit_time")),
            include_submit_time_feature=bool(data.get("include_submit_time_feature", True)),
            extra_text_columns=tuple(data.get("extra_text_columns", ()) or ()),
            extra_char_limit=int(data.get("extra_char_limit", 2000)),
            instruction=str(data.get("instruction", instruction)),
        )
    except LeakageError as exc:
        raise typer.BadParameter(str(exc)) from exc


def embed(
    input_path: Annotated[
        Path, typer.Argument(exists=True, readable=True, help="Ingested job parquet")
    ],
    out: Annotated[Path, typer.Option("--out", help="Output embedded parquet path")],
    model: Annotated[
        str, typer.Option("--model", help="'stub' or a sentence-transformers model id")
    ] = "stub",
    text_format: Annotated[str, typer.Option("--format", help="prose | kv")] = "prose",
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Local YAML (extra_text_columns, instruction, ...)"),
    ] = None,
    device: Annotated[str, typer.Option("--device")] = "auto",
    dtype: Annotated[str, typer.Option("--dtype")] = "fp16",
    batch_size: Annotated[int, typer.Option("--batch-size")] = 32,
    chunk_size: Annotated[int, typer.Option("--chunk-size", help="Rows per cache chunk")] = 1000,
    cache_dir: Annotated[
        Path | None, typer.Option("--cache-dir", help="Vector cache dir (enables resume)")
    ] = None,
    instruction: Annotated[str, typer.Option("--instruction")] = "",
    trust_remote_code: Annotated[bool, typer.Option("--trust-remote-code")] = False,
) -> None:
    """Embed an ingested job table into an embedded parquet + provenance manifest."""
    from hpc_oda_commons.embeddings.runner import embed_table

    config = _load_config(config_path, text_format, instruction)
    try:
        encoder = build_encoder(
            model,
            device=device,
            dtype=dtype,
            batch_size=batch_size,
            trust_remote_code=trust_remote_code,
        )
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc

    console.print(
        f"[blue]embed[/blue] {input_path} -> {out}  model={encoder.info.model_id} "
        f"dim={encoder.info.dim} format={config.text_format}"
    )

    state = {"last": -1}

    def _progress(done: int, total: int, elapsed: float) -> None:
        pct = int(100 * done / total)
        if pct >= state["last"] + 10 or done == total:
            state["last"] = pct
            rate = done / elapsed if elapsed > 0 else 0.0
            # `total` is the count of *unique* texts (duplicates are embedded once).
            console.print(f"  {done}/{total} unique ({pct}%)  {rate:.1f} emb/s")

    manifest = embed_table(
        input_path,
        out,
        encoder,
        config,
        cache_dir=cache_dir,
        chunk_size=chunk_size,
        on_progress=_progress,
    )
    console.print(
        f"[green]done[/green]: {manifest['row_count']} rows "
        f"({manifest['unique_text_count']} unique, "
        f"{manifest['duplicate_ratio']:.0%} duplicate), "
        f"dim {manifest['embedding_dim']}; manifest {out}.manifest.json"
    )
