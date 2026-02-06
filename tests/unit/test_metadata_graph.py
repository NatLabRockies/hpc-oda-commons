from __future__ import annotations

from hpc_oda_commons.intelligence.metadata_graph import build_metadata_graph_payload


def test_build_metadata_graph_payload() -> None:
    graph = build_metadata_graph_payload()
    nodes = {n["id"]: n for n in graph["nodes"]}
    assert "adapter.slurmctld" in nodes
    assert any(edge["type"] == "has_domain" for edge in graph["edges"])
