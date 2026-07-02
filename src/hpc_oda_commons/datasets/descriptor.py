"""
Dataset descriptors (`oda.dataset.v0.1.0`).

A descriptor is a declarative, per-dataset ETL spec: where the data lives and how
to fetch it (with checksums + slices), how to decode it, and how to normalize it
into one or more canonical ODA tables. Descriptors are validated against the
`oda.dataset.v0.1.0` JSON Schema plus the cross-field rules in
:func:`validate_descriptor`.

This module is the P1 foundation: the model + validation only. Fetch/decode/
normalize (P2/P3) and registry catalog integration (P4) build on top of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from hpc_oda_commons.kernel.validate import SchemaValidationError, validate_json

DATASET_SCHEMA_ID = "oda.dataset.v0.1.0"


@dataclass(frozen=True)
class Capability:
    """A model-suitability claim: this target drives `problem_domain` via `target_column`."""

    problem_domain: str
    target_column: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Capability:
        return cls(
            problem_domain=str(payload.get("problem_domain")),
            target_column=str(payload.get("target_column")),
        )


@dataclass(frozen=True)
class Target:
    """One canonical output table produced from the source data."""

    schema: str
    mapping: Mapping[str, Any]
    output_id: str
    output_path: str
    capabilities: tuple[Capability, ...] = ()
    suitable_models: tuple[str, ...] = ()
    select: tuple[str, ...] = ()
    filter: Mapping[str, Any] | None = None
    sample: Mapping[str, Any] | None = None

    @property
    def produced_columns(self) -> frozenset[str]:
        """Canonical column names this target emits (the keys of `mapping`)."""
        return frozenset(self.mapping.keys())

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Target:
        output = payload.get("output") or {}
        return cls(
            schema=str(payload.get("schema")),
            mapping=dict(payload.get("mapping") or {}),
            output_id=str(output.get("id")),
            output_path=str(output.get("path")),
            capabilities=tuple(
                Capability.from_dict(c) for c in (payload.get("capabilities") or [])
            ),
            suitable_models=tuple(str(m) for m in (payload.get("suitable_models") or [])),
            select=tuple(str(s) for s in (payload.get("select") or [])),
            filter=payload.get("filter"),
            sample=payload.get("sample"),
        )


@dataclass(frozen=True)
class Descriptor:
    """A validated `oda.dataset.v0.1.0` descriptor."""

    dataset_id: str
    name: str
    version: str
    description: str
    problem_domains: tuple[str, ...]
    source: Mapping[str, Any]
    decode: Mapping[str, Any]
    targets: tuple[Target, ...]
    license: Mapping[str, Any] | None = None
    tags: tuple[str, ...] = ()
    size: Mapping[str, Any] | None = None
    systems: tuple[str, ...] = ()
    providers: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> Descriptor:
        return cls(
            dataset_id=str(payload.get("dataset_id")),
            name=str(payload.get("name")),
            version=str(payload.get("version")),
            description=str(payload.get("description")),
            problem_domains=tuple(str(d) for d in (payload.get("problem_domains") or [])),
            source=dict(payload.get("source") or {}),
            decode=dict(payload.get("decode") or {}),
            targets=tuple(Target.from_dict(t) for t in (payload.get("targets") or [])),
            license=payload.get("license"),
            tags=tuple(str(t) for t in (payload.get("tags") or [])),
            size=payload.get("size"),
            systems=tuple(str(s) for s in (payload.get("systems") or [])),
            providers=tuple(str(p) for p in (payload.get("providers") or [])),
        )

    def capabilities(self) -> tuple[Capability, ...]:
        """All capabilities across every target."""
        return tuple(cap for target in self.targets for cap in target.capabilities)

    def supports_domain(self, domain: str) -> bool:
        return domain in self.problem_domains

    def supports_model(self, model_id: str) -> bool:
        return any(model_id in target.suitable_models for target in self.targets)


def load_descriptor(path: Path, *, validate: bool = True) -> Descriptor:
    """Load a descriptor YAML from `path`, validating it unless `validate=False`."""
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SchemaValidationError(
            schema_id=DATASET_SCHEMA_ID,
            message="Dataset descriptor YAML must be a mapping/object.",
            path=str(path),
        )
    if validate:
        validate_descriptor(payload, path=path)
    return Descriptor.from_dict(payload)


def validate_descriptor(payload: Mapping[str, Any], *, path: Path | None = None) -> None:
    """Validate a descriptor against the JSON Schema plus cross-field rules."""
    validate_json(dict(payload), DATASET_SCHEMA_ID, path=path)
    loc = str(path) if path else None

    declared_domains = {str(d) for d in (payload.get("problem_domains") or [])}

    for idx, target in enumerate(payload.get("targets") or []):
        produced = set((target.get("mapping") or {}).keys())
        for cap in target.get("capabilities") or []:
            column = cap.get("target_column")
            if column not in produced:
                raise SchemaValidationError(
                    schema_id=DATASET_SCHEMA_ID,
                    message=(
                        f"targets[{idx}] declares capability target_column "
                        f"'{column}' that its mapping does not produce."
                    ),
                    path=loc,
                )
            domain = cap.get("problem_domain")
            if domain not in declared_domains:
                raise SchemaValidationError(
                    schema_id=DATASET_SCHEMA_ID,
                    message=(
                        f"targets[{idx}] capability problem_domain '{domain}' is "
                        "not listed in the dataset's problem_domains."
                    ),
                    path=loc,
                )

        sample = target.get("sample")
        if sample and sample.get("strategy") == "stratified" and not sample.get("by"):
            raise SchemaValidationError(
                schema_id=DATASET_SCHEMA_ID,
                message=f"targets[{idx}].sample uses 'stratified' strategy but sets no 'by'.",
                path=loc,
            )

    source = payload.get("source") or {}
    if source.get("kind") != "manual":
        for j, resource in enumerate(source.get("resources") or []):
            if not resource.get("url"):
                raise SchemaValidationError(
                    schema_id=DATASET_SCHEMA_ID,
                    message=(
                        f"source.resources[{j}] requires a url for kind '{source.get('kind')}'."
                    ),
                    path=loc,
                )

    slices = source.get("slices")
    if slices:
        default = slices.get("default")
        available = slices.get("available") or {}
        if default not in available:
            raise SchemaValidationError(
                schema_id=DATASET_SCHEMA_ID,
                message=f"source.slices.default '{default}' is not in slices.available.",
                path=loc,
            )
