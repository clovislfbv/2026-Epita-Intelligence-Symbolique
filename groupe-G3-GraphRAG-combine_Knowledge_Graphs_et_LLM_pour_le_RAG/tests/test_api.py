"""Tests for the GraphRAG FastAPI backend (app/main.py)."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def reset_state():
    """Reset shared application state before each test.

    Ensures that the knowledge graph, docs_map, and active_dataset are
    returned to their initial values so tests do not interfere with each
    other.
    """
    from app.main import state
    state["kg"] = None
    state["docs_map"] = {}
    state["active_dataset"] = "custom"


@pytest.fixture
def client():
    """Create a FastAPI TestClient for the application.

    Returns:
        A TestClient wrapping the FastAPI app instance from app.main.
    """
    from app.main import app
    return TestClient(app)


def test_query_without_kg_400(client):
    """POST /query returns 400 when the knowledge graph has not been built."""
    assert client.post("/query", json={"question": "test"}).status_code == 400


def test_graph_overview_without_kg_404(client):
    """GET /graph/overview returns 404 when the knowledge graph has not been built."""
    assert client.get("/graph/overview").status_code == 404


def test_graph_community_without_kg_404(client):
    """GET /graph/community/{id} returns 404 when the knowledge graph has not been built."""
    assert client.get("/graph/community/0").status_code == 404


def test_graph_node_neighbors_without_kg_404(client):
    """GET /graph/node/{name}/neighbors returns 404 when the knowledge graph has not been built."""
    assert client.get("/graph/node/Alice/neighbors").status_code == 404


def test_graph_overview_with_kg(client):
    """GET /graph/overview returns community sizes and stats once the KG is built."""
    from graphrag_core.extractor import Triple
    from graphrag_core.graph import build_knowledge_graph
    from app.main import state
    state["kg"] = build_knowledge_graph(
        [Triple("Alice", "WORKS_AT", "ACME"), Triple("Alice", "KNOWS", "Bob")], {}
    )
    r = client.get("/graph/overview")
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["node_count"] == 3
    assert len(body["communities"]) >= 1


def test_graph_community_with_kg(client):
    """GET /graph/community/{id} returns nodes/edges for that community."""
    from graphrag_core.extractor import Triple
    from graphrag_core.graph import build_knowledge_graph
    from app.main import state
    state["kg"] = build_knowledge_graph(
        [Triple("Alice", "WORKS_AT", "ACME"), Triple("Alice", "KNOWS", "Bob")], {}
    )
    cid = state["kg"].node_to_community["Alice"]
    r = client.get(f"/graph/community/{cid}")
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body and "edges" in body
    assert body["truncated"] is False


def test_graph_node_neighbors_with_kg(client):
    """GET /graph/node/{name}/neighbors returns the node's direct neighbors."""
    from graphrag_core.extractor import Triple
    from graphrag_core.graph import build_knowledge_graph
    from app.main import state
    state["kg"] = build_knowledge_graph(
        [Triple("Alice", "WORKS_AT", "ACME"), Triple("Alice", "KNOWS", "Bob")], {}
    )
    r = client.get("/graph/node/Alice/neighbors")
    assert r.status_code == 200
    ids = {n["id"] for n in r.json()["nodes"]}
    assert ids == {"ACME", "Bob"}


def test_dataset_select_valid(client):
    """POST /dataset/select returns 200 and the active dataset name for a valid dataset."""
    r = client.post("/dataset/select", json={"dataset": "hotpotqa"})
    assert r.status_code == 200
    assert r.json()["active"] == "hotpotqa"


def test_dataset_select_invalid_400(client):
    """POST /dataset/select returns 400 for an unknown dataset identifier."""
    assert client.post("/dataset/select", json={"dataset": "bad"}).status_code == 400


def test_list_datasets_structure(client):
    """GET /datasets returns 200 with 'active' and 'datasets' keys."""
    r = client.get("/datasets")
    assert r.status_code == 200
    body = r.json()
    assert "active" in body and "datasets" in body


def test_query_with_kg(client):
    """POST /query returns a valid QueryResponse when the KG is pre-populated."""
    from graphrag_core.extractor import Triple
    from graphrag_core.graph import build_knowledge_graph
    from app.main import state
    state["kg"] = build_knowledge_graph([Triple("Alice", "WORKS_AT", "ACME")], {})
    state["docs_map"] = {"f.txt": "Alice works at ACME."}
    with patch("app.main.get_llm_client") as mock:
        mock.return_value.complete.return_value = "Alice works at ACME."
        r = client.post("/query", json={"question": "Where does Alice work?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Alice works at ACME."
    assert "trace" in body
    assert "subgraph_nodes" in body
