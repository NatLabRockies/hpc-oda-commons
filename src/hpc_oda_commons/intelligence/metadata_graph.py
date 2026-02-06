from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hpc_oda_commons.registry.models import RegistrySnapshot
from hpc_oda_commons.registry.snapshot import load_registry_snapshot


@dataclass(frozen=True)
class GraphNode:
    id: str
    type: str
    label: str


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    type: str


def build_metadata_graph(snapshot: RegistrySnapshot) -> dict[str, Any]:
    nodes: dict[str, GraphNode] = {}
    edges: list[GraphEdge] = []

    def _add_node(node_id: str, node_type: str, label: str) -> None:
        nodes.setdefault(node_id, GraphNode(id=node_id, type=node_type, label=label))

    for entry in snapshot.entries:
        _add_node(entry.id, "entry", entry.name)

        for tag in entry.tags:
            node_id = f"tag:{tag}"
            _add_node(node_id, "tag", tag)
            edges.append(GraphEdge(source=entry.id, target=node_id, type="has_tag"))

        for domain in entry.problem_domain:
            node_id = f"domain:{domain}"
            _add_node(node_id, "domain", domain)
            edges.append(GraphEdge(source=entry.id, target=node_id, type="has_domain"))

        for source in entry.supported_sources:
            node_id = f"source:{source}"
            _add_node(node_id, "source", source)
            edges.append(GraphEdge(source=entry.id, target=node_id, type="supports_source"))

        if entry.input_schema_version:
            node_id = f"schema:{entry.input_schema_version}"
            _add_node(node_id, "schema", entry.input_schema_version)
            edges.append(GraphEdge(source=entry.id, target=node_id, type="input_schema"))

        if entry.output_schema_version:
            node_id = f"schema:{entry.output_schema_version}"
            _add_node(node_id, "schema", entry.output_schema_version)
            edges.append(GraphEdge(source=entry.id, target=node_id, type="output_schema"))

    node_list = [nodes[k] for k in sorted(nodes.keys())]
    edge_list = sorted(edges, key=lambda e: (e.source, e.type, e.target))

    return {
        "nodes": [node.__dict__ for node in node_list],
        "edges": [edge.__dict__ for edge in edge_list],
    }


def build_metadata_graph_payload(path: str | None = None) -> dict[str, Any]:
    snapshot = load_registry_snapshot(path)
    return build_metadata_graph(snapshot)
