from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AdapterMetadata:
    id: str
    name: str
    version: str
    input_schema_version: str | None
    output_schema_version: str | None
    supported_sources: tuple[str, ...]


def adapter_metadata(folder: Path) -> AdapterMetadata:
    """An adapter's metadata, read from the ``adapter.yml`` beside its code.

    The same file the registry is built from (#249), so the two can't disagree. The id
    comes from the folder's name.
    """
    import yaml

    meta = yaml.safe_load((folder / "adapter.yml").read_text(encoding="utf-8")) or {}
    return AdapterMetadata(
        id=f"adapter.{folder.name}",
        name=str(meta["name"]),
        version=str(meta["version"]),
        input_schema_version=meta.get("input_schema_version"),
        output_schema_version=meta.get("output_schema_version"),
        supported_sources=tuple(meta.get("supported_sources") or ()),
    )


@runtime_checkable
class SourceAdapter(Protocol):
    metadata: AdapterMetadata

    def parse(self, path: Path) -> list[dict[str, Any]]:
        """Parse a source input into ODA schema-aligned rows."""
