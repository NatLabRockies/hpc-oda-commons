"""
Metadata models for adapters/models/tools/recipes (registry entries).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping


@dataclass(frozen=True)
class RegistryReference:
    kind: Literal["python", "path"]
    module: str | None = None
    object: str | None = None
    path: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegistryReference":
        kind = payload.get("kind")
        if kind not in ("python", "path"):
            raise ValueError(f"Unknown reference kind: {kind!r}")

        if kind == "python":
            python = payload.get("python") or {}
            module = python.get("module")
            obj = python.get("object")
            if not module or not obj:
                raise ValueError("python reference requires module and object")
            return cls(kind="python", module=str(module), object=str(obj))

        path = payload.get("path")
        if not path:
            raise ValueError("path reference requires path")
        return cls(kind="path", path=str(path))


@dataclass(frozen=True)
class RegistryEntry:
    id: str
    entry_type: Literal["adapter", "model", "recipe"]
    name: str
    version: str
    description: str
    problem_domain: tuple[str, ...]
    supported_sources: tuple[str, ...] = ()
    input_schema_version: str | None = None
    output_schema_version: str | None = None
    license: str | None = None
    dependencies: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    reference: RegistryReference | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegistryEntry":
        entry_type = payload.get("entry_type")
        if entry_type not in ("adapter", "model", "recipe"):
            raise ValueError(f"Invalid entry_type: {entry_type!r}")

        problem_domain = tuple(str(tag) for tag in (payload.get("problem_domain") or []))
        supported_sources = tuple(str(src) for src in (payload.get("supported_sources") or []))
        dependencies = tuple(str(dep) for dep in (payload.get("dependencies") or []))
        tags = tuple(str(tag) for tag in (payload.get("tags") or []))
        reference = payload.get("reference")

        return cls(
            id=str(payload.get("id")),
            entry_type=entry_type,
            name=str(payload.get("name")),
            version=str(payload.get("version")),
            description=str(payload.get("description")),
            problem_domain=problem_domain,
            supported_sources=supported_sources,
            input_schema_version=payload.get("input_schema_version"),
            output_schema_version=payload.get("output_schema_version"),
            license=payload.get("license"),
            dependencies=dependencies,
            tags=tags,
            reference=RegistryReference.from_dict(reference) if reference else None,
        )

    def has_tag(self, tag: str) -> bool:
        return tag in self.tags or tag in self.problem_domain

    def supports_source(self, source: str) -> bool:
        return source in self.supported_sources


@dataclass(frozen=True)
class RegistrySnapshot:
    schema_version: str
    generated_at: str
    entries: tuple[RegistryEntry, ...]
    source: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "RegistrySnapshot":
        entries = tuple(RegistryEntry.from_dict(e) for e in (payload.get("entries") or []))
        return cls(
            schema_version=str(payload.get("schema_version")),
            generated_at=str(payload.get("generated_at")),
            source=payload.get("source"),
            entries=entries,
        )


def entries_by_type(
    entries: Iterable[RegistryEntry], entry_type: Literal["adapter", "model", "recipe"]
) -> tuple[RegistryEntry, ...]:
    return tuple(e for e in entries if e.entry_type == entry_type)
