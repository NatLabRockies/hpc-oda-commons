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


@runtime_checkable
class SourceAdapter(Protocol):
    metadata: AdapterMetadata

    def parse(self, path: Path) -> list[dict[str, Any]]:
        """Parse a source input into ODA schema-aligned rows."""
