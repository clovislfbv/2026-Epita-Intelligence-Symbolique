from graphrag_core.extractor import Triple
from graphrag_core.graph import build_knowledge_graph, graph_to_json

TRIPLES = [
    Triple("Alice", "WORKS_AT", "ACME"),
    Triple("Alice", "KNOWS", "Bob"),
    Triple("Bob", "WORKS_AT", "TechCorp"),
]


def test_nodes_present():
    """All entity names from triples appear as nodes in the nx_graph."""
    kg = build_knowledge_graph(TRIPLES, {})
    for name in ("Alice", "ACME", "Bob", "TechCorp"):
        assert name in kg.nx_graph.nodes()


def test_edges_present():
    """Edges derived from triples exist in the nx_graph."""
    kg = build_knowledge_graph(TRIPLES, {})
    assert kg.nx_graph.has_edge("Alice", "ACME")
    assert kg.nx_graph.has_edge("Bob", "TechCorp")


def test_communities_cover_all_nodes():
    """Every node belongs to exactly one community."""
    kg = build_knowledge_graph(TRIPLES, {})
    assert len(kg.communities) >= 1
    covered = {n for c in kg.communities for n in c.nodes}
    assert covered == set(kg.nx_graph.nodes())


def test_node_to_community_complete():
    """node_to_community maps every node to a community id."""
    kg = build_knowledge_graph(TRIPLES, {})
    for node in kg.nx_graph.nodes():
        assert node in kg.node_to_community


def test_graph_to_json_structure():
    """graph_to_json returns the expected keys and correct stat counts."""
    kg = build_knowledge_graph(TRIPLES, {})
    data = graph_to_json(kg)
    assert data["stats"]["node_count"] == 4
    assert data["stats"]["edge_count"] == 3
    assert "nodes" in data and "edges" in data and "communities" in data


def test_empty_graph():
    """An empty triple list produces a graph with zero nodes and communities."""
    kg = build_knowledge_graph([], {})
    data = graph_to_json(kg)
    assert data["stats"]["node_count"] == 0
    assert data["stats"]["community_count"] == 0


def test_community_overview_structure():
    """community_overview returns per-community size/color and global stats."""
    from graphrag_core.graph import community_overview
    kg = build_knowledge_graph(TRIPLES, {})
    data = community_overview(kg)
    assert "communities" in data and "stats" in data
    assert data["stats"]["node_count"] == 4
    total_size = sum(c["size"] for c in data["communities"])
    assert total_size == 4
    for c in data["communities"]:
        assert set(c.keys()) == {"id", "label", "size", "color"}


def test_community_detail_returns_members():
    """community_detail returns the community's nodes, untruncated when under the limit."""
    from graphrag_core.graph import community_detail
    kg = build_knowledge_graph(TRIPLES, {})
    cid = kg.node_to_community["Alice"]
    data = community_detail(kg, cid)
    ids = {n["id"] for n in data["nodes"]}
    assert "Alice" in ids
    assert data["truncated"] is False
    assert "edges" in data


def test_community_detail_truncates_with_limit():
    """community_detail truncates to `limit`, sorted by degree descending, and reports the total."""
    from graphrag_core.graph import community_detail
    kg = build_knowledge_graph(TRIPLES, {})
    cid = kg.node_to_community["Alice"]
    data = community_detail(kg, cid, limit=1)
    assert len(data["nodes"]) == 1
    assert data["truncated"] is True
    assert data["total_in_community"] >= 2


def test_community_detail_unknown_id_empty():
    """community_detail returns an empty result for a community id that doesn't exist."""
    from graphrag_core.graph import community_detail
    kg = build_knowledge_graph(TRIPLES, {})
    data = community_detail(kg, 9999)
    assert data["nodes"] == []
    assert data["edges"] == []
    assert data["truncated"] is False


def test_node_neighbors_excludes_self():
    """node_neighbors returns only the neighbors, never the queried node itself."""
    from graphrag_core.graph import node_neighbors
    kg = build_knowledge_graph(TRIPLES, {})
    data = node_neighbors(kg, "Alice")
    ids = {n["id"] for n in data["nodes"]}
    assert "Alice" not in ids
    assert ids == {"ACME", "Bob"}
    assert data["truncated"] is False


def test_node_neighbors_unknown_node_empty():
    """node_neighbors returns an empty result for a node absent from the graph."""
    from graphrag_core.graph import node_neighbors
    kg = build_knowledge_graph(TRIPLES, {})
    assert node_neighbors(kg, "Nobody") == {"nodes": [], "edges": [], "truncated": False}


def test_node_neighbors_truncates_with_limit():
    """node_neighbors truncates to `limit` and reports truncated=True."""
    from graphrag_core.graph import node_neighbors
    kg = build_knowledge_graph(TRIPLES, {})
    data = node_neighbors(kg, "Alice", limit=1)
    assert len(data["nodes"]) == 1
    assert data["truncated"] is True
