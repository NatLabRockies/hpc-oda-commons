from __future__ import annotations

from pathlib import Path

from hpc_oda_commons.kernel.hashing import hash_input
from hpc_oda_commons.kernel.provenance import build_provenance


def test_hash_input(tmp_path: Path) -> None:
    p = tmp_path / "x.txt"
    p.write_text("hello", encoding="utf-8")
    hi = hash_input(p)
    assert hi.path.endswith("x.txt")
    assert hi.sha256 is not None
    assert hi.size_bytes == 5


def test_build_provenance(tmp_path: Path) -> None:
    p = tmp_path / "data.bin"
    p.write_bytes(b"abc")
    prov = build_provenance(
        input_schema="oda.job.v0.1.0",
        result_schema="oda.result.v0.1.0",
        inputs=[p],
        capture_packages=False,
    )
    assert prov["schema_versions"]["input"] == "oda.job.v0.1.0"
    assert prov["schema_versions"]["result"] == "oda.result.v0.1.0"
    assert prov["environment"]["python"]
    assert isinstance(prov["inputs"], list) and prov["inputs"][0]["sha256"]
