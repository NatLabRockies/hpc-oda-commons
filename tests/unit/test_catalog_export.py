from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from hpc_oda_commons.catalog import (
    CatalogExportError,
    export_catalog,
    iter_registered_descriptors,
    to_croissant,
)
from hpc_oda_commons.qst.cli import app

SHA = "a" * 64


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "dataset_id": "dataset.job_runtime.demo",
        "name": "Demo Jobs",
        "version": "1.2.0",
        "description": "A small demo job table.",
        "problem_domains": ["job-runtime-prediction"],
        "systems": ["Demo"],
        "providers": ["Demo Lab"],
        "citation": {"doi": "10.1234/demo"},
        "license": {"spdx": "CC-BY-4.0"},
        "tags": ["demo"],
        "source": {
            "kind": "http",
            "resources": [
                {
                    "filename": "jobs.parquet",
                    "url": "https://example.org/jobs.parquet",
                    "sha256": SHA,
                    "bytes": 123,
                }
            ],
        },
        "targets": [
            {
                "schema": "oda.job.v0.2.0",
                "mapping": {
                    "job_id": {"from": "id"},
                    "start_time": {"from": "start"},
                    "runtime_seconds": {"derive": "end_time - start_time"},
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_core_fields() -> None:
    record = to_croissant(_payload())
    assert record["@id"] == record["citeAs"] == "https://doi.org/10.1234/demo"
    assert record["license"] == "https://spdx.org/licenses/CC-BY-4.0.html"
    assert record["keywords"] == ["demo", "job-runtime-prediction"]  # "Demo" deduplicated
    (dist,) = record["distribution"]
    assert dist["sha256"] == SHA
    assert dist["encodingFormat"] == "application/x-parquet"
    assert dist["contentSize"] == "123 B"


def test_record_set_lists_only_directly_sourced_columns() -> None:
    record = to_croissant(_payload())
    (record_set,) = record["recordSet"]
    assert [f["name"] for f in record_set["field"]] == ["job_id", "start_time"]
    assert record["oda:canonicalFields"]["oda.job.v0.2.0"] == [
        "job_id",
        "start_time",
        "runtime_seconds",
    ]


def test_no_record_set_for_archives() -> None:
    payload = _payload()
    payload["source"]["resources"][0]["filename"] = "jobs.zip"
    assert "recordSet" not in to_croissant(payload)


def test_gated_source_points_at_provider_page() -> None:
    payload = _payload(
        citation={"url": "https://provider.example/data"},
        license={"spdx": "LicenseRef-provider", "gated": True, "notes": "Form required."},
    )
    payload["source"] = {"kind": "manual", "resources": [{"filename": "a.csv.gz", "sha256": SHA}]}
    record = to_croissant(payload)
    assert record["distribution"][0]["contentUrl"] == "https://provider.example/data"
    assert record["oda:gated"] is True
    assert record["license"] == "LicenseRef-provider — Form required."


def test_every_registered_descriptor_exports(tmp_path: Path) -> None:
    payloads = list(iter_registered_descriptors())
    written = export_catalog(tmp_path, payloads=payloads)
    assert len(written) == len(payloads) > 0
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert len(index["datasets"]) == len(payloads)


def test_unknown_dataset_id_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CatalogExportError, match="nope"):
        export_catalog(tmp_path, payloads=[_payload()], dataset_ids=["nope"])


def test_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    ok = runner.invoke(
        app, ["catalog", "export", "-o", str(tmp_path), "-d", "dataset.job_runtime.pm100"]
    )
    assert ok.exit_code == 0, ok.output
    assert (tmp_path / "dataset.job_runtime.pm100.json").is_file()
    assert (
        runner.invoke(app, ["catalog", "export", "-o", str(tmp_path), "-d", "nope"]).exit_code == 2
    )
