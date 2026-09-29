"""Export dataset descriptors as MLCommons Croissant 1.0 catalog records.

Records are built from the bundled descriptors only: no network access, no data files read.
"""

from __future__ import annotations

import importlib.resources as ir
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from hpc_oda_commons.datasets.descriptor import validate_descriptor
from hpc_oda_commons.registry.snapshot import load_registry_snapshot

CROISSANT_CONFORMS_TO = "http://mlcommons.org/croissant/1.0"
ODA_NAMESPACE = "https://github.com/NatLabRockies/hpc-oda-commons/ns#"

# The standard Croissant 1.0 JSON-LD context (required by the spec), plus the `oda:` prefix.
CROISSANT_CONTEXT: dict[str, Any] = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "citeAs": "cr:citeAs",
    "column": "cr:column",
    "conformsTo": "dct:conformsTo",
    "cr": "http://mlcommons.org/croissant/",
    "rai": "http://mlcommons.org/croissant/RAI/",
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "dct": "http://purl.org/dc/terms/",
    "examples": {"@id": "cr:examples", "@type": "@json"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileProperty": "cr:fileProperty",
    "fileObject": "cr:fileObject",
    "fileSet": "cr:fileSet",
    "format": "cr:format",
    "includes": "cr:includes",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "md5": "cr:md5",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "sc": "https://schema.org/",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
    "oda": ODA_NAMESPACE,
}

_MEDIA_TYPES = (
    (".parquet", "application/x-parquet"),
    (".gz", "application/gzip"),
    (".zip", "application/zip"),
    (".csv", "text/csv"),
    (".json", "application/json"),
)
_TABULAR = {"application/x-parquet", "text/csv"}


class CatalogExportError(ValueError):
    """Raised for unknown dataset ids."""


@dataclass(frozen=True)
class ExportedRecord:
    dataset_id: str
    path: Path


def _doi_url(doi: str) -> str:
    return doi if doi.startswith("http") else f"https://doi.org/{doi.removeprefix('doi:')}"


def _landing_page(payload: Mapping[str, Any]) -> str:
    citation = payload.get("citation") or {}
    if citation.get("url"):
        return str(citation["url"])
    if citation.get("doi"):
        return _doi_url(str(citation["doi"]))
    return f"https://github.com/NatLabRockies/hpc-oda-commons#{payload['dataset_id']}"


def _license(payload: Mapping[str, Any]) -> str:
    lic = payload.get("license") or {}
    spdx = str(lic.get("spdx") or "unspecified")
    if lic.get("url"):
        return str(lic["url"])
    if not spdx.startswith("LicenseRef-") and spdx != "unspecified":
        return f"https://spdx.org/licenses/{spdx}.html"
    return f"{spdx} — {lic['notes']}" if lic.get("notes") else spdx


def _media_type(filename: str) -> str:
    name = filename.lower()
    return next(
        (mime for ext, mime in _MEDIA_TYPES if name.endswith(ext)), "application/octet-stream"
    )


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-") or "file"


def _data_type(column: str) -> str:
    col = column.lower()
    if col.endswith("_time"):
        return "sc:DateTime"
    if col == "job_id":
        return "sc:Text"
    if any(h in col for h in ("seconds", "memory", "power", "energy", "_mb", "_gb")):
        return "sc:Float"
    if any(h in col for h in ("cpus", "gpus", "nodes", "cores", "tasks", "exit_code")):
        return "sc:Integer"
    return "sc:Text"


def _keywords(payload: Mapping[str, Any]) -> list[str]:
    seen: dict[str, str] = {}
    for group in ("tags", "systems", "problem_domains"):
        for item in payload.get(group) or []:
            seen.setdefault(str(item).lower(), str(item))
    return list(seen.values())


def to_croissant(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Build a Croissant 1.0 JSON-LD record from a descriptor payload."""
    dataset_id = str(payload["dataset_id"])
    source = payload.get("source") or {}
    landing = _landing_page(payload)
    gated = bool((payload.get("license") or {}).get("gated")) or source.get("kind") == "manual"

    distribution = []
    for res in source.get("resources") or []:
        filename = str(res["filename"])
        entry: dict[str, Any] = {
            "@type": "cr:FileObject",
            "@id": _slug(filename),
            "name": filename,
            "contentUrl": str(res.get("url") or landing),  # gated files: provider's page
            "encodingFormat": _media_type(filename),
            "sha256": str(res["sha256"]),
        }
        if res.get("bytes") is not None:
            entry["contentSize"] = f"{int(res['bytes'])} B"
        distribution.append(entry)

    # Croissant requires every Field to name its source column, so a RecordSet lists only
    # columns copied directly from a single tabular file. All canonical columns go in
    # oda:canonicalFields.
    single_file = (
        distribution[0]["@id"]
        if len(distribution) == 1 and distribution[0]["encodingFormat"] in _TABULAR
        else None
    )
    record_sets = []
    canonical: dict[str, list[str]] = {}
    for target in payload.get("targets") or []:
        schema_id = str(target.get("schema"))
        mapping = target.get("mapping") or {}
        canonical[schema_id] = [str(c) for c in mapping]
        fields = [
            {
                "@type": "cr:Field",
                "@id": f"{schema_id}/{column}",
                "name": str(column),
                "dataType": _data_type(str(column)),
                "source": {"fileObject": {"@id": single_file}, "extract": {"column": rule["from"]}},
            }
            for column, rule in mapping.items()
            if single_file and isinstance(rule, Mapping) and isinstance(rule.get("from"), str)
        ]
        if fields:
            record_sets.append(
                {"@type": "cr:RecordSet", "@id": schema_id, "name": schema_id, "field": fields}
            )

    description = " ".join(str(payload.get("description") or "").split())
    citation = payload.get("citation") or {}
    record: dict[str, Any] = {
        "@context": CROISSANT_CONTEXT,
        "@type": "sc:Dataset",
        "conformsTo": CROISSANT_CONFORMS_TO,
        "@id": _doi_url(str(citation["doi"])) if citation.get("doi") else dataset_id,
        "name": str(payload["name"]),
        "description": description,
        "url": landing,
        "citeAs": _doi_url(str(citation["doi"])) if citation.get("doi") else landing,
        "license": _license(payload),
        "version": str(payload.get("version") or "1.0.0"),
        "keywords": _keywords(payload),
        "creator": [
            {"@type": "sc:Organization", "name": p} for p in payload.get("providers") or []
        ],
        "distribution": distribution,
        "oda:datasetId": dataset_id,
        "oda:problemDomains": list(payload.get("problem_domains") or []),
        "oda:systems": list(payload.get("systems") or []),
        "oda:canonicalFields": canonical,
        "oda:gated": gated,
    }
    if record_sets:
        record["recordSet"] = record_sets
    return record


def iter_registered_descriptors() -> Iterator[dict[str, Any]]:
    """Yield every validated descriptor payload registered in the bundled snapshot."""
    base = ir.files("hpc_oda_commons")
    for entry in load_registry_snapshot().entries:
        rel = entry.reference.path if entry.reference else None
        if entry.entry_type != "dataset" or not rel or not rel.startswith("hpc_oda_commons/"):
            continue
        path = Path(str(base / rel.removeprefix("hpc_oda_commons/")))
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        validate_descriptor(payload, path=path)
        yield payload


def export_catalog(
    out_dir: Path,
    *,
    dataset_ids: Iterable[str] | None = None,
    payloads: Iterable[Mapping[str, Any]] | None = None,
) -> list[ExportedRecord]:
    """Write `<dataset_id>.json` per dataset plus `index.json` to `out_dir`."""
    source = list(payloads) if payloads is not None else list(iter_registered_descriptors())
    wanted = set(dataset_ids or ())
    missing = wanted - {str(p["dataset_id"]) for p in source}
    if missing:
        raise CatalogExportError(f"Unknown dataset id(s): {', '.join(sorted(missing))}")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for payload in sorted(source, key=lambda p: str(p["dataset_id"])):
        dataset_id = str(payload["dataset_id"])
        if wanted and dataset_id not in wanted:
            continue
        path = out_dir / f"{dataset_id}.json"
        _write_json(path, to_croissant(payload))
        written.append(ExportedRecord(dataset_id, path))
    _write_json(
        out_dir / "index.json",
        {
            "conformsTo": CROISSANT_CONFORMS_TO,
            "datasets": [{"dataset_id": r.dataset_id, "path": r.path.name} for r in written],
        },
    )
    return written


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
