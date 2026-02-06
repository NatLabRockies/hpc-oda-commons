"""
In-memory indices and filtering logic (tags, schema compat, etc.).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hpc_oda_commons.registry.models import RegistryEntry


@dataclass(frozen=True)
class RegistryIndex:
    entries: tuple[RegistryEntry, ...]
    by_id: dict[str, RegistryEntry]

    @classmethod
    def from_entries(cls, entries: Iterable[RegistryEntry]) -> RegistryIndex:
        entries_tuple = tuple(entries)
        by_id = {entry.id: entry for entry in entries_tuple}
        return cls(entries=entries_tuple, by_id=by_id)

    def get(self, entry_id: str) -> RegistryEntry | None:
        return self.by_id.get(entry_id)

    def filter(
        self,
        *,
        tag: str | None = None,
        entry_type: str | None = None,
        source: str | None = None,
        input_schema: str | None = None,
        output_schema: str | None = None,
    ) -> tuple[RegistryEntry, ...]:
        filtered = self.entries
        if entry_type:
            filtered = tuple(e for e in filtered if e.entry_type == entry_type)
        if tag:
            filtered = tuple(e for e in filtered if e.has_tag(tag))
        if source:
            filtered = tuple(e for e in filtered if e.supports_source(source))
        if input_schema:
            filtered = tuple(e for e in filtered if e.input_schema_version == input_schema)
        if output_schema:
            filtered = tuple(e for e in filtered if e.output_schema_version == output_schema)
        return filtered
