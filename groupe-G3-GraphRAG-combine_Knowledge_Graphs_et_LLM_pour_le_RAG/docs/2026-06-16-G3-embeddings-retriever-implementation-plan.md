# Embeddings-Based Entity Resolution and Hybrid Retriever Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every entity a vector embedding, auto-merge near-duplicate entity names before the graph is built, and let the retriever find seed entities by meaning (not just exact keyword match) before running its existing BFS.

**Architecture:** A new `graphrag_core/embeddings.py` module wraps a local `sentence-transformers` model behind a single `embed_texts()` function. `graph.py` gains `resolve_entities()`, called once per build/import to merge near-duplicate names and produce a `{name: vector}` map stored on `KnowledgeGraph`. `retriever.py` gains `semantic_seed_entities()`, which reuses that map plus the question's own embedding to find BFS seeds the existing keyword matcher misses.

**Tech Stack:** `sentence-transformers` (new), `numpy` (already transitive via scikit-learn), existing FastAPI SSE build pipeline.

**Reference spec:** `docs/2026-06-16-G3-graph-viz-embeddings-retriever-design.md`, sections 3 and 4.

**Depends on:** none of the other plan's tasks — independent of `docs/2026-06-16-G3-graph-viz-implementation-plan.md`. Can be implemented before, after, or in parallel with it.

---

## File Map

```
graphrag_core/embeddings.py     (create — local embedding model wrapper)
graphrag_core/graph.py          (modify — MergeEvent, resolve_entities, node_embeddings field)
graphrag_core/retriever.py      (modify — semantic_seed_entities)
graphrag_core/pipeline.py       (modify — union seeds before BFS)
app/main.py                     (modify — entity_resolution SSE stage, wire into /build and /import)
app/static/app.js               (modify — add entity_resolution to STAGES)
app/static/index.html           (modify — add entity_resolution progress row)
pyproject.toml / uv.lock        (modify — add sentence-transformers dependency)
tests/test_embeddings.py        (create)
tests/test_graph.py             (modify — resolve_entities tests)
tests/test_retriever.py         (modify — semantic_seed_entities tests)
tests/test_pipeline.py          (modify — hybrid seed union test)
```

---

### Task 1: Add the `sentence-transformers` dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

- [ ] **Step 1: Add the dependency**

```bash
uv add sentence-transformers
```

This updates both `pyproject.toml` and `uv.lock`. Expect a larger `uv.lock` diff since `torch` is a transitive dependency.

- [ ] **Step 2: Verify the import works**

```bash
uv run python -c "import sentence_transformers; print('ok')"
```

Expected: `ok` (this will trigger a one-time download of pip packages, not the model weights yet — the model itself downloads on first `SentenceTransformer(...)` instantiation, which happens in Task 2).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(G3): add sentence-transformers dependency"
```

---

### Task 2: `graphrag_core/embeddings.py`

**Files:**
- Create: `graphrag_core/embeddings.py`
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_embeddings.py`:

```python
"""Tests for the local sentence-embedding wrapper."""

from unittest.mock import patch, MagicMock

import numpy as np


def test_embed_texts_empty_list_returns_empty_array():
    """embed_texts on an empty list returns a (0, 384) array without loading the model."""
    from graphrag_core.embeddings import embed_texts
    result = embed_texts([])
    assert result.shape == (0, 384)


def test_embed_texts_calls_model_and_returns_its_output():
    """embed_texts delegates to the cached model with normalization enabled."""
    with patch("graphrag_core.embeddings._get_model") as mock_get_model:
        mock_model = MagicMock()
        mock_model.encode.return_value = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        mock_get_model.return_value = mock_model

        from graphrag_core.embeddings import embed_texts
        result = embed_texts(["Alice", "Bob"])

        mock_model.encode.assert_called_once_with(
            ["Alice", "Bob"], normalize_embeddings=True, convert_to_numpy=True
        )
        assert result.shape == (2, 2)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'graphrag_core.embeddings'`

- [ ] **Step 3: Implement `graphrag_core/embeddings.py`**

```python
"""Local sentence-embedding utilities shared by entity resolution and the retriever.

Exposes a single function, ``embed_texts``, backed by a lazily-loaded,
process-wide ``sentence-transformers`` model so the (relatively expensive)
model load happens at most once per process, regardless of how many times
a build or query needs embeddings.
"""

from typing import List

import numpy as np

_MODEL_NAME = "all-MiniLM-L6-v2"
_EMBEDDING_DIM = 384
_model = None


def _get_model():
    """Lazily load and cache the sentence-transformers model as a module-level singleton.

    Returns:
        A loaded ``SentenceTransformer`` instance, reused across calls.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed_texts(texts: List[str]) -> np.ndarray:
    """Encode a batch of strings into L2-normalized embedding vectors.

    Args:
        texts: The strings to encode. May be empty.

    Returns:
        A float32 array of shape ``(len(texts), 384)``. Each row has unit
        L2 norm, so the cosine similarity between any two rows is simply
        their dot product. Returns shape ``(0, 384)`` for an empty input,
        without loading the model.
    """
    if not texts:
        return np.zeros((0, _EMBEDDING_DIM), dtype=np.float32)
    model = _get_model()
    vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    return vectors.astype(np.float32)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add graphrag_core/embeddings.py tests/test_embeddings.py
git commit -m "feat(G3): add local sentence-embedding wrapper"
```

---

### Task 3: `resolve_entities` and `node_embeddings` in `graph.py`

**Files:**
- Modify: `graphrag_core/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_graph.py`:

```python
def test_resolve_entities_merges_similar_names(monkeypatch):
    """resolve_entities merges a name into an earlier-seen near-duplicate above the threshold."""
    import numpy as np
    from graphrag_core.graph import resolve_entities

    def fake_embed(texts):
        vectors = {
            "Barack Obama": np.array([0.95, 0.3122, 0, 0, 0, 0], dtype=np.float32),
            "Hawaii": np.array([0, 0, 1, 0, 0, 0], dtype=np.float32),
            "Obama": np.array([1.0, 0, 0, 0, 0, 0], dtype=np.float32),
            "President": np.array([0, 0, 0, 1, 0, 0], dtype=np.float32),
            "Paris": np.array([0, 0, 0, 0, 1, 0], dtype=np.float32),
            "France": np.array([0, 0, 0, 0, 0, 1], dtype=np.float32),
        }
        return np.stack([vectors[t] for t in texts])

    monkeypatch.setattr("graphrag_core.graph.embed_texts", fake_embed)

    triples = [
        Triple("Barack Obama", "BORN_IN", "Hawaii"),
        Triple("Obama", "HELD_POSITION", "President"),
        Triple("Paris", "LOCATED_IN", "France"),
    ]
    resolved, merges, embeddings = resolve_entities(triples, threshold=0.90)

    names = {t.subject for t in resolved} | {t.object for t in resolved}
    assert "Obama" not in names
    assert "Barack Obama" in names
    assert len(merges) == 1
    assert merges[0].alias == "Obama"
    assert merges[0].canonical == "Barack Obama"
    assert "Barack Obama" in embeddings
    assert "Obama" not in embeddings


def test_resolve_entities_no_merge_below_threshold(monkeypatch):
    """resolve_entities leaves dissimilar names untouched."""
    import numpy as np
    from graphrag_core.graph import resolve_entities

    def fake_embed(texts):
        vectors = {
            "Alice": np.array([1.0, 0.0], dtype=np.float32),
            "Bob": np.array([0.0, 1.0], dtype=np.float32),
        }
        return np.stack([vectors[t] for t in texts])

    monkeypatch.setattr("graphrag_core.graph.embed_texts", fake_embed)

    triples = [Triple("Alice", "KNOWS", "Bob")]
    resolved, merges, embeddings = resolve_entities(triples, threshold=0.90)
    assert merges == []
    assert resolved == triples
    assert set(embeddings.keys()) == {"Alice", "Bob"}


def test_resolve_entities_empty_input():
    """resolve_entities on an empty triple list returns empty everything, no embedding calls."""
    from graphrag_core.graph import resolve_entities
    resolved, merges, embeddings = resolve_entities([])
    assert resolved == []
    assert merges == []
    assert embeddings == {}


def test_build_knowledge_graph_stores_node_embeddings():
    """build_knowledge_graph attaches a passed-in node_embeddings dict to the KG."""
    import numpy as np
    vec = np.array([1.0, 0.0], dtype=np.float32)
    kg = build_knowledge_graph(TRIPLES, {}, node_embeddings={"Alice": vec})
    assert "Alice" in kg.node_embeddings


def test_build_knowledge_graph_defaults_to_empty_embeddings():
    """build_knowledge_graph defaults node_embeddings to {} when not provided."""
    kg = build_knowledge_graph(TRIPLES, {})
    assert kg.node_embeddings == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph.py -k "resolve_entities or node_embeddings" -v`
Expected: FAIL — `resolve_entities` doesn't exist, `node_embeddings` keyword arg not accepted.

- [ ] **Step 3: Update imports and the `KnowledgeGraph` dataclass**

In `graphrag_core/graph.py`, change the top imports from:

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any

import networkx as nx
from rdflib import Graph as RDFGraph, Namespace, URIRef

from .extractor import Triple
```

to:

```python
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Set, Optional

import networkx as nx
import numpy as np
from rdflib import Graph as RDFGraph, Namespace, URIRef

from .embeddings import embed_texts
from .extractor import Triple
```

Then add `node_embeddings` to the `KnowledgeGraph` dataclass — change:

```python
@dataclass
class KnowledgeGraph:
    """A fully constructed knowledge graph with community structure.

    Attributes:
        rdf: An RDFLib Graph containing the triples as RDF statements.
        nx_graph: A directed NetworkX graph where nodes are entity names
            and edges carry a ``relation`` attribute.
        communities: List of Community instances produced by community
            detection.
        node_to_community: Mapping from node name to the id of its
            community.
    """

    rdf: RDFGraph
    nx_graph: nx.DiGraph
    communities: List[Community]
    node_to_community: Dict[str, int]
```

to:

```python
@dataclass
class KnowledgeGraph:
    """A fully constructed knowledge graph with community structure.

    Attributes:
        rdf: An RDFLib Graph containing the triples as RDF statements.
        nx_graph: A directed NetworkX graph where nodes are entity names
            and edges carry a ``relation`` attribute.
        communities: List of Community instances produced by community
            detection.
        node_to_community: Mapping from node name to the id of its
            community.
        node_embeddings: Mapping from node name to its embedding vector,
            as produced by ``resolve_entities``. Empty when the graph was
            built without entity resolution.
    """

    rdf: RDFGraph
    nx_graph: nx.DiGraph
    communities: List[Community]
    node_to_community: Dict[str, int]
    node_embeddings: Dict[str, np.ndarray] = field(default_factory=dict)
```

- [ ] **Step 4: Update `build_knowledge_graph` to accept and store `node_embeddings`**

Change:

```python
def build_knowledge_graph(triples: List[Triple], docs_map: Dict[str, str]) -> KnowledgeGraph:
```

to:

```python
def build_knowledge_graph(
    triples: List[Triple],
    docs_map: Dict[str, str],
    node_embeddings: Optional[Dict[str, np.ndarray]] = None,
) -> KnowledgeGraph:
```

And update its docstring `Args:` section to add:

```
        node_embeddings: Optional mapping from node name to embedding
            vector, typically produced by ``resolve_entities`` on the same
            *triples* before calling this function. Defaults to an empty
            dict when not provided.
```

And change its final `return` statement from:

```python
    return KnowledgeGraph(rdf=rdf, nx_graph=G, communities=communities, node_to_community=node_to_comm)
```

to:

```python
    return KnowledgeGraph(
        rdf=rdf,
        nx_graph=G,
        communities=communities,
        node_to_community=node_to_comm,
        node_embeddings=node_embeddings or {},
    )
```

- [ ] **Step 5: Implement `MergeEvent` and `resolve_entities`**

Add to `graphrag_core/graph.py`, after the `Community` dataclass:

```python
@dataclass
class MergeEvent:
    """A record of one entity name being merged into a canonical node.

    Attributes:
        alias: The entity name that was folded into another node.
        canonical: The entity name that absorbed the alias.
        similarity: The cosine similarity that triggered the merge.
    """

    alias: str
    canonical: str
    similarity: float
```

Add to `graphrag_core/graph.py`, after `build_knowledge_graph` (before `_detect_communities`):

```python
def resolve_entities(
    triples: List[Triple], threshold: float = 0.90
) -> Tuple[List[Triple], List[MergeEvent], Dict[str, np.ndarray]]:
    """Merge near-duplicate entity names before building the graph.

    Every unique subject/object name across *triples* is embedded once.
    Names are then visited in first-occurrence order; each name is compared
    (cosine similarity) against the embeddings of names already accepted as
    canonical. A name at or above *threshold* similarity to an existing
    canonical name is rewritten to that canonical name everywhere it
    appears; otherwise it becomes a new canonical name itself.

    Args:
        triples: The extracted triples to resolve.
        threshold: Minimum cosine similarity for two names to be merged.
            Defaults to 0.90.

    Returns:
        A tuple of:
        - the rewritten triples, deduplicated the same way
          ``extract_triples`` deduplicates (triples that became identical
          after renaming are collapsed to one),
        - the list of ``MergeEvent`` records describing every merge
          performed, in the order they happened,
        - a dict mapping each canonical name to its embedding vector,
          ready to pass as ``build_knowledge_graph``'s ``node_embeddings``.
    """
    names: List[str] = []
    seen_names: Set[str] = set()
    for t in triples:
        for n in (t.subject, t.object):
            if n not in seen_names:
                seen_names.add(n)
                names.append(n)

    if not names:
        return [], [], {}

    vectors = embed_texts(names)

    canonical_names: List[str] = []
    canonical_vectors: List[np.ndarray] = []
    rename_map: Dict[str, str] = {}
    merges: List[MergeEvent] = []

    for name, vec in zip(names, vectors):
        if canonical_vectors:
            sims = np.stack(canonical_vectors) @ vec
            best_idx = int(np.argmax(sims))
            best_sim = float(sims[best_idx])
        else:
            best_sim = -1.0
            best_idx = -1

        if best_sim >= threshold:
            canonical = canonical_names[best_idx]
            rename_map[name] = canonical
            merges.append(MergeEvent(alias=name, canonical=canonical, similarity=best_sim))
        else:
            rename_map[name] = name
            canonical_names.append(name)
            canonical_vectors.append(vec)

    seen_triples: Set[Triple] = set()
    resolved: List[Triple] = []
    for t in triples:
        rt = Triple(rename_map[t.subject], t.relation, rename_map[t.object])
        if rt not in seen_triples:
            seen_triples.add(rt)
            resolved.append(rt)

    embeddings = dict(zip(canonical_names, canonical_vectors))
    return resolved, merges, embeddings
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_graph.py -v`
Expected: all tests pass (existing tests + the 5 new ones from this task)

- [ ] **Step 7: Commit**

```bash
git add graphrag_core/graph.py tests/test_graph.py
git commit -m "feat(G3): add resolve_entities for embedding-based entity dedup"
```

---

### Task 4: Wire entity resolution into the build and import flows

**Files:**
- Modify: `app/main.py`
- Modify: `app/static/app.js`
- Modify: `app/static/index.html`

No new automated tests in this task — `_build_gen` and `/import` are already covered by the existing test suite (which doesn't assert on SSE message content), and the design spec calls for manual verification of the live merge messages (Task 5 of this plan).

- [ ] **Step 1: Update the import line in `app/main.py`**

Change:

```python
from graphrag_core.graph import build_knowledge_graph, graph_to_json
```

to:

```python
from graphrag_core.graph import build_knowledge_graph, graph_to_json, resolve_entities
```

(This line was already extended once in the graph-viz plan to add `community_overview`, `community_detail`, `node_neighbors` — if that plan ran first, add `resolve_entities` to that same import tuple instead of duplicating the line.)

- [ ] **Step 2: Insert the entity-resolution stage in `_build_gen`**

In `app/main.py`, inside `_build_gen`, find:

```python
        yield _sse("extraction", 40, f"{len(all_triples)} triples extracted")
        yield _sse("graph_build", 50, "Building RDF graph…")
        await asyncio.sleep(0)
        yield _sse("community_detection", 70, "Community detection (Leiden)…")
        await asyncio.sleep(0)
        kg = build_knowledge_graph(all_triples, docs_map)
```

Replace with:

```python
        yield _sse("extraction", 40, f"{len(all_triples)} triples extracted")
        yield _sse("entity_resolution", 45, "Resolving entities…")
        await asyncio.sleep(0)
        all_triples, merges, embeddings = resolve_entities(all_triples)
        for m in merges:
            yield _sse(
                "entity_resolution", 48,
                f"{m.alias} → merged into {m.canonical} ({m.similarity:.2f})",
            )
            await asyncio.sleep(0)
        yield _sse("graph_build", 50, "Building RDF graph…")
        await asyncio.sleep(0)
        yield _sse("community_detection", 70, "Community detection (Leiden)…")
        await asyncio.sleep(0)
        kg = build_knowledge_graph(all_triples, docs_map, node_embeddings=embeddings)
```

- [ ] **Step 3: Wire it into `/import`**

In `app/main.py`, find the `import_kg` function body:

```python
    from graphrag_core.extractor import Triple
    triples = [Triple(t["subject"], t["relation"], t["object"]) for t in triples_data]
    kg = build_knowledge_graph(triples, docs_map)
```

Replace with:

```python
    from graphrag_core.extractor import Triple
    triples = [Triple(t["subject"], t["relation"], t["object"]) for t in triples_data]
    triples, _merges, embeddings = resolve_entities(triples)
    kg = build_knowledge_graph(triples, docs_map, node_embeddings=embeddings)
```

- [ ] **Step 4: Add the new stage to the frontend progress checklist**

In `app/static/index.html`, find:

```html
        <div class="prog-step" id="prog-extraction"><div class="prog-dot"></div>Entity extraction</div>
        <div class="prog-step" id="prog-graph_build"><div class="prog-dot"></div>RDF graph construction</div>
```

Insert a new row between them:

```html
        <div class="prog-step" id="prog-extraction"><div class="prog-dot"></div>Entity extraction</div>
        <div class="prog-step" id="prog-entity_resolution"><div class="prog-dot"></div>Entity resolution</div>
        <div class="prog-step" id="prog-graph_build"><div class="prog-dot"></div>RDF graph construction</div>
```

In `app/static/app.js`, find:

```javascript
const STAGES = ['extraction', 'graph_build', 'community_detection', 'indexing'];
```

Replace with:

```javascript
const STAGES = ['extraction', 'entity_resolution', 'graph_build', 'community_detection', 'indexing'];
```

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest tests/ -v`
Expected: all tests still pass (no test asserts on SSE stage names or counts).

- [ ] **Step 6: Commit**

```bash
git add app/main.py app/static/app.js app/static/index.html
git commit -m "feat(G3): stream entity-resolution merges during KG build, run on import too"
```

---

### Task 5: `semantic_seed_entities` in `retriever.py`

**Files:**
- Modify: `graphrag_core/retriever.py`
- Test: `tests/test_retriever.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_retriever.py`:

```python
def test_semantic_seed_entities_returns_top_k(monkeypatch):
    """semantic_seed_entities returns the top_k nodes most similar to the question."""
    import numpy as np
    from graphrag_core.retriever import semantic_seed_entities

    kg = _kg()
    kg.node_embeddings.update({
        "Alice": np.array([1.0, 0.0], dtype=np.float32),
        "Bob": np.array([0.9, 0.1], dtype=np.float32) / np.linalg.norm([0.9, 0.1]),
        "Paris": np.array([0.0, 1.0], dtype=np.float32),
    })

    def fake_embed(texts):
        return np.array([[1.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("graphrag_core.retriever.embed_texts", fake_embed)

    seeds = semantic_seed_entities("question about Alice", kg, top_k=2, min_similarity=0.3)
    assert seeds == ["Alice", "Bob"]


def test_semantic_seed_entities_filters_below_floor(monkeypatch):
    """semantic_seed_entities drops candidates below min_similarity."""
    import numpy as np
    from graphrag_core.retriever import semantic_seed_entities

    kg = _kg()
    kg.node_embeddings.update({
        "Alice": np.array([1.0, 0.0], dtype=np.float32),
        "Paris": np.array([0.0, 1.0], dtype=np.float32),
    })

    def fake_embed(texts):
        return np.array([[1.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("graphrag_core.retriever.embed_texts", fake_embed)

    seeds = semantic_seed_entities("question", kg, top_k=5, min_similarity=0.5)
    assert seeds == ["Alice"]


def test_semantic_seed_entities_empty_when_no_embeddings():
    """semantic_seed_entities returns [] when the KG has no node_embeddings."""
    from graphrag_core.retriever import semantic_seed_entities
    assert semantic_seed_entities("anything", _kg(), top_k=5) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_retriever.py -k semantic_seed -v`
Expected: FAIL with `ImportError: cannot import name 'semantic_seed_entities'`

- [ ] **Step 3: Implement `semantic_seed_entities`**

In `graphrag_core/retriever.py`, change the top imports from:

```python
from dataclasses import dataclass, field
from typing import List, Set

from .graph import KnowledgeGraph
```

to:

```python
from dataclasses import dataclass, field
from typing import List, Set

import numpy as np

from .embeddings import embed_texts
from .graph import KnowledgeGraph
```

Add this function after `detect_entities`:

```python
def semantic_seed_entities(
    question: str, kg: KnowledgeGraph, top_k: int = 5, min_similarity: float = 0.3
) -> List[str]:
    """Find seed entities by embedding similarity rather than exact keyword match.

    Catches paraphrased references that detect_entities cannot — e.g. a
    question describing an entity ("the director of Sinister") rather than
    naming it ("Scott Derrickson"). min_similarity acts as a floor so that
    a question unrelated to anything in the graph doesn't still return
    top_k arbitrary nodes.

    Args:
        question: The natural language question to embed.
        kg: The KnowledgeGraph whose node_embeddings are searched.
        top_k: Maximum number of seed entities to return. Defaults to 5.
        min_similarity: Minimum cosine similarity required to be returned
            at all. Defaults to 0.3.

    Returns:
        Up to top_k node names, ordered by similarity to the question
        (highest first). Empty if the KG has no node_embeddings.
    """
    if not kg.node_embeddings:
        return []

    names = list(kg.node_embeddings.keys())
    matrix = np.stack([kg.node_embeddings[n] for n in names])
    query_vec = embed_texts([question])[0]
    sims = matrix @ query_vec

    ranked = sorted(zip(names, sims), key=lambda pair: pair[1], reverse=True)
    return [name for name, sim in ranked[:top_k] if sim >= min_similarity]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_retriever.py -v`
Expected: all tests pass (existing tests + the 3 new ones)

- [ ] **Step 5: Commit**

```bash
git add graphrag_core/retriever.py tests/test_retriever.py
git commit -m "feat(G3): add semantic_seed_entities for embedding-based seed search"
```

---

### Task 6: Union semantic and keyword seeds in `pipeline.py`

**Files:**
- Modify: `graphrag_core/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_pipeline.py`. Note that `embed_texts` is called from inside `semantic_seed_entities` in `retriever.py`, so that is where it must be patched — not in `pipeline.py`:

```python
def test_run_unions_keyword_and_semantic_seeds(monkeypatch):
    """run() includes semantic seeds even when the keyword match misses them."""
    import numpy as np
    from graphrag_core.pipeline import run

    kg = _kg()
    kg.node_embeddings.update({
        "Alice": np.array([1.0, 0.0], dtype=np.float32),
        "Bob": np.array([1.0, 0.0], dtype=np.float32),
    })

    def fake_embed(texts):
        return np.array([[1.0, 0.0]], dtype=np.float32)

    monkeypatch.setattr("graphrag_core.retriever.embed_texts", fake_embed)

    # "Bob" never appears as text in the question, so detect_entities alone
    # would miss it — only the semantic path can surface it as a seed.
    result = run("Tell me about this person", kg, _llm(), max_hops=1)
    assert "Bob" in result.subgraph_nodes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline.py::test_run_unions_keyword_and_semantic_seeds -v`
Expected: FAIL — `result.subgraph_nodes` does not contain "Bob" yet (no semantic path wired in).

- [ ] **Step 3: Update `pipeline.py`**

In `graphrag_core/pipeline.py`, change:

```python
from .llm import LLMClient
from .graph import KnowledgeGraph
from .retriever import TraceStep, detect_entities, extract_subgraph, subgraph_to_context
```

to:

```python
from .llm import LLMClient
from .graph import KnowledgeGraph
from .retriever import (
    TraceStep,
    detect_entities,
    extract_subgraph,
    semantic_seed_entities,
    subgraph_to_context,
)
```

Then change:

```python
    seeds = detect_entities(question, kg)
    subgraph = extract_subgraph(kg, seeds, max_hops=max_hops, max_nodes=max_nodes)
```

to:

```python
    seeds = list(set(detect_entities(question, kg)) | set(semantic_seed_entities(question, kg)))
    if not seeds:
        degrees = dict(kg.nx_graph.degree())
        seeds = sorted(degrees, key=degrees.get, reverse=True)[:3]
    subgraph = extract_subgraph(kg, seeds, max_hops=max_hops, max_nodes=max_nodes)
```

Also update the docstring's numbered steps — change:

```
    1. **Entity detection** — scan the question for KG node names.
```

to:

```
    1. **Entity detection** — scan the question for KG node names (exact
       keyword match) and search node_embeddings by question similarity
       (semantic match); the seed set is their union. Falls back to the
       top-3 highest-degree nodes if both find nothing.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pipeline.py -v`
Expected: all tests pass (existing tests + the new one). The existing `test_run_no_entity_match_uses_fallback` test (if present) should still pass since the fallback logic is preserved, just moved one level up to wrap the unioned seed set instead of only `detect_entities`'s result.

- [ ] **Step 5: Commit**

```bash
git add graphrag_core/pipeline.py tests/test_pipeline.py
git commit -m "feat(G3): union keyword and semantic seeds before BFS in the pipeline"
```

---

### Task 7: Manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 2: Build a dataset and watch entity resolution live**

```bash
uvicorn app.main:app --reload --port 8000
```

In the browser, select the `custom` dataset, upload a short text file that mentions the same entity two different ways (e.g. one paragraph saying "Barack Obama was president." and another saying "Obama was born in Hawaii."), then click "Build Knowledge Graph". Confirm the progress panel shows an "Entity resolution" step and, if names were close enough to merge, a message like `Obama → merged into Barack Obama (0.9x)`.

- [ ] **Step 3: Confirm the merge is reflected in the graph**

Open the Knowledge Graph tab (or, if Plan 1 hasn't been implemented yet, `GET /graph` if it still exists, or `GET /graph/overview` + drill in) and confirm there is exactly one node for the merged entity, not two.

- [ ] **Step 4: Confirm semantic retrieval improves a paraphrased question**

Ask a question that describes an entity without naming it exactly as it appears in the graph (e.g., for the HotpotQA dataset, a question referencing "the director of" a film rather than the director's name). Confirm the answer's trace (chip → drawer) includes hops that a pure keyword match on the question text could not have found — i.e. the entity reached doesn't literally appear as a substring of the question.
