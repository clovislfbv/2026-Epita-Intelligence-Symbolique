# Clickable Graph Visualization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-graph D3 force-directed render (unusable at 30k+ nodes) with a community-bubble overview that drills down on click, and lets the user grow the view by clicking nodes to reveal their neighbors.

**Architecture:** Three new backend read endpoints (`/graph/overview`, `/graph/community/{id}`, `/graph/node/{name}/neighbors`) replace the old `GET /graph`, each returning a bounded payload regardless of total graph size. The frontend keeps one D3 force-directed renderer but feeds it progressively-loaded, mutated-in-place data so existing node positions survive each expansion.

**Tech Stack:** FastAPI, NetworkX (existing), D3.js v7 (existing), pytest + FastAPI TestClient.

**Reference spec:** `docs/2026-06-16-G3-graph-viz-embeddings-retriever-design.md`, section 2.

---

## File Map

```
graphrag_core/graph.py          (modify — add community_overview, community_detail, node_neighbors)
app/main.py                     (modify — replace GET /graph with 3 routes)
app/static/app.js               (modify — overview/detail rendering, click-to-expand, Q&A focus)
app/static/index.html           (modify — back button, load-more button)
app/static/style.css            (modify — bubble + button styles)
tests/test_graph.py             (modify — tests for the 3 new graph.py functions)
tests/test_api.py               (modify — tests for the 3 new routes, remove old /graph tests)
```

---

### Task 1: `community_overview` in `graph.py`

**Files:**
- Modify: `graphrag_core/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph.py` (append at the end of the file):

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_graph.py::test_community_overview_structure -v`
Expected: FAIL with `ImportError: cannot import name 'community_overview'`

- [ ] **Step 3: Implement `community_overview`**

Add to `graphrag_core/graph.py`, after the `graph_to_json` function:

```python
def community_overview(kg: KnowledgeGraph) -> Dict[str, Any]:
    """Serialise only the community-level summary of a KnowledgeGraph.

    Unlike graph_to_json, this never lists individual nodes — the payload
    size depends only on the number of communities, not on graph size.

    Args:
        kg: The KnowledgeGraph to summarise.

    Returns:
        A dict with ``communities`` (list of id/label/size/color dicts) and
        ``stats`` (the same node/edge/community counts as graph_to_json).
    """
    sizes: Dict[int, int] = {}
    for cid in kg.node_to_community.values():
        sizes[cid] = sizes.get(cid, 0) + 1
    communities = [
        {
            "id": c.id,
            "label": c.label,
            "size": sizes.get(c.id, 0),
            "color": _COLORS[c.id % len(_COLORS)],
        }
        for c in kg.communities
    ]
    return {
        "communities": communities,
        "stats": {
            "node_count": kg.nx_graph.number_of_nodes(),
            "edge_count": kg.nx_graph.number_of_edges(),
            "community_count": len(kg.communities),
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_graph.py::test_community_overview_structure -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add graphrag_core/graph.py tests/test_graph.py
git commit -m "feat(G3): add community_overview for lightweight graph summary"
```

---

### Task 2: `community_detail` in `graph.py`

**Files:**
- Modify: `graphrag_core/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_graph.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph.py -k community_detail -v`
Expected: FAIL with `ImportError: cannot import name 'community_detail'`

- [ ] **Step 3: Implement `community_detail`**

Add to `graphrag_core/graph.py`, after `community_overview`:

```python
def community_detail(kg: KnowledgeGraph, community_id: int, limit: int = 150) -> Dict[str, Any]:
    """Serialise a single community's nodes and internal edges.

    Nodes are sorted by degree (descending) and truncated to *limit* so the
    payload stays bounded even for very large communities.

    Args:
        kg: The KnowledgeGraph to read from.
        community_id: The id of the community to expand.
        limit: Maximum number of nodes to return. Defaults to 150.

    Returns:
        A dict with ``nodes`` (id/community/color/degree dicts), ``edges``
        (source/target/relation dicts between returned nodes only),
        ``truncated`` (whether the community has more members than
        *limit*), and ``total_in_community`` (the untruncated member count).
    """
    members: List[str] = next((c.nodes for c in kg.communities if c.id == community_id), [])
    G = kg.nx_graph
    members_sorted = sorted(members, key=lambda n: G.degree(n), reverse=True)
    total = len(members_sorted)
    selected = members_sorted[:limit]
    selected_set = set(selected)

    nodes = [
        {
            "id": n,
            "community": community_id,
            "color": _COLORS[community_id % len(_COLORS)],
            "degree": G.degree(n),
        }
        for n in selected
    ]
    edges = [
        {"source": u, "target": v, "relation": d.get("relation", "")}
        for u, v, d in G.edges(data=True)
        if u in selected_set and v in selected_set
    ]
    return {
        "nodes": nodes,
        "edges": edges,
        "truncated": total > limit,
        "total_in_community": total,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graph.py -k community_detail -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add graphrag_core/graph.py tests/test_graph.py
git commit -m "feat(G3): add community_detail for bounded community expansion"
```

---

### Task 3: `node_neighbors` in `graph.py`

**Files:**
- Modify: `graphrag_core/graph.py`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_graph.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_graph.py -k node_neighbors -v`
Expected: FAIL with `ImportError: cannot import name 'node_neighbors'`

- [ ] **Step 3: Implement `node_neighbors`**

Add to `graphrag_core/graph.py`, after `community_detail`:

```python
def node_neighbors(kg: KnowledgeGraph, node_name: str, limit: int = 40) -> Dict[str, Any]:
    """Serialise the immediate (1-hop) neighbors of a single node.

    The queried node itself is never included in the result — only its
    neighbors and the edges directly connecting it to each of them.

    Args:
        kg: The KnowledgeGraph to read from.
        node_name: The node to expand.
        limit: Maximum number of neighbors to return, highest-degree first.
            Defaults to 40.

    Returns:
        A dict with ``nodes``, ``edges`` (each edge has one endpoint equal
        to *node_name*), and ``truncated``. All empty/False if *node_name*
        is not in the graph.
    """
    G = kg.nx_graph
    if node_name not in G:
        return {"nodes": [], "edges": [], "truncated": False}

    raw_edges = [(node_name, d.get("relation", ""), nbr) for _, nbr, d in G.out_edges(node_name, data=True)]
    raw_edges += [(pred, d.get("relation", ""), node_name) for pred, _, d in G.in_edges(node_name, data=True)]

    neighbors = list(dict.fromkeys(tgt if src == node_name else src for src, _, tgt in raw_edges))
    neighbors.sort(key=lambda n: G.degree(n), reverse=True)
    total = len(neighbors)
    selected = set(neighbors[:limit])

    nodes = [
        {
            "id": n,
            "community": kg.node_to_community.get(n, 0),
            "color": _COLORS[kg.node_to_community.get(n, 0) % len(_COLORS)],
            "degree": G.degree(n),
        }
        for n in neighbors[:limit]
    ]

    seen_e = set()
    edges = []
    for src, rel, tgt in raw_edges:
        other = tgt if src == node_name else src
        if other not in selected:
            continue
        key = (src, rel, tgt)
        if key in seen_e:
            continue
        seen_e.add(key)
        edges.append({"source": src, "target": tgt, "relation": rel})

    return {"nodes": nodes, "edges": edges, "truncated": total > limit}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_graph.py -k node_neighbors -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add graphrag_core/graph.py tests/test_graph.py
git commit -m "feat(G3): add node_neighbors for 1-hop click-to-expand"
```

---

### Task 4: Replace `GET /graph` with the 3 new routes in `app/main.py`

**Files:**
- Modify: `app/main.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

In `tests/test_api.py`, replace the `test_graph_without_kg_404` function with:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_api.py -k graph -v`
Expected: FAIL — old `/graph` route still exists, new routes 404 with "Not Found" (no route registered) instead of the KG-not-built 404.

- [ ] **Step 3: Replace the route in `app/main.py`**

Change the import line:

```python
from graphrag_core.graph import build_knowledge_graph, graph_to_json
```

to:

```python
from graphrag_core.graph import (
    build_knowledge_graph,
    graph_to_json,
    community_overview,
    community_detail,
    node_neighbors,
)
```

Replace the `GET /graph` route (the `@app.get("/graph")` function block) with:

```python
@app.get("/graph/overview")
async def graph_overview():
    """Return the community-level summary of the knowledge graph.

    Returns:
        A dict with ``communities`` and ``stats``, regardless of graph size.

    Raises:
        HTTPException: 404 if the knowledge graph has not been built yet.
    """
    if state["kg"] is None:
        raise HTTPException(404, "KG not built")
    return community_overview(state["kg"])


@app.get("/graph/community/{community_id}")
async def graph_community(community_id: int, limit: int = 150):
    """Return the nodes and internal edges of a single community.

    Args:
        community_id: The id of the community to expand.
        limit: Maximum number of nodes to return, highest-degree first.

    Returns:
        A dict with ``nodes``, ``edges``, ``truncated``, and
        ``total_in_community``.

    Raises:
        HTTPException: 404 if the knowledge graph has not been built yet.
    """
    if state["kg"] is None:
        raise HTTPException(404, "KG not built")
    return community_detail(state["kg"], community_id, limit)


@app.get("/graph/node/{node_name}/neighbors")
async def graph_node_neighbors(node_name: str, limit: int = 40):
    """Return the immediate neighbors of a single node.

    Args:
        node_name: The node to expand.
        limit: Maximum number of neighbors to return, highest-degree first.

    Returns:
        A dict with ``nodes``, ``edges``, and ``truncated``.

    Raises:
        HTTPException: 404 if the knowledge graph has not been built yet.
    """
    if state["kg"] is None:
        raise HTTPException(404, "KG not built")
    return node_neighbors(state["kg"], node_name, limit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_api.py -v`
Expected: all tests pass (old `/graph` tests are gone, new ones pass)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat(G3): replace GET /graph with overview/community/neighbors routes"
```

---

### Task 5: Frontend — community bubble overview

**Files:**
- Modify: `app/static/app.js`
- Modify: `app/static/index.html`
- Modify: `app/static/style.css`

No automated test exists for the frontend in this repo (no JS test runner is configured) — verification for this task and the remaining frontend tasks is manual, via the running app in a browser, done at the end in Task 8.

- [ ] **Step 1: Add toolbar buttons to `index.html`**

In `app/static/index.html`, inside `<div class="graph-toolbar">`, before `<div class="live-dot"></div>`, add:

```html
<button class="graph-back-btn" id="graph-back-btn" style="display:none">← Overview</button>
```

And after the `comm-filters-wrap` closing `</div>` (still inside `.graph-toolbar`), add:

```html
<button class="load-more-btn" id="load-more-btn" style="display:none">Load 150 more ↓</button>
```

- [ ] **Step 2: Add CSS for the bubbles and buttons to `style.css`**

Append to `app/static/style.css`:

```css
.graph-back-btn,.load-more-btn{font-size:11px;font-weight:600;color:#6366f1;background:transparent;border:1px solid rgba(99,102,241,.25);border-radius:20px;padding:5px 12px;cursor:pointer;white-space:nowrap}
.graph-back-btn{background:#eef2ff}
.graph-back-btn:hover,.load-more-btn:hover{background:#e0e7ff}
.comm-bubble{cursor:pointer}
.comm-bubble text{pointer-events:none}
```

- [ ] **Step 3: Replace `loadGraph` with `loadGraphOverview` and add `renderOverview` in `app.js`**

In `app/static/app.js`, replace the entire `loadGraph` function (the one that calls `GET /graph`) with:

```javascript
let viewMode = 'overview';
let overviewData = null;
let currentCommunityId = null;
let currentLimit = 150;

/**
 * Fetches the community-level overview and renders it as clickable bubbles.
 */
async function loadGraphOverview() {
  try {
    const data = await (await fetch(`${API}/graph/overview`)).json();
    overviewData = data;
    viewMode = 'overview';
    document.getElementById('graph-back-btn').style.display = 'none';
    document.getElementById('load-more-btn').style.display = 'none';
    renderOverview(data);
    renderCommunityFilters(data.communities);
    document.getElementById('stat-nodes').textContent = data.stats.node_count;
    document.getElementById('stat-edges').textContent = data.stats.edge_count;
    document.getElementById('stat-comms').textContent = data.stats.community_count;
  } catch (_) {}
}

/**
 * Renders one circle per community, sized by member count, via a D3 pack layout.
 * @param {Object} data - Response from GET /graph/overview.
 */
function renderOverview(data) {
  const svg = d3.select('#graph-svg');
  svg.selectAll('*').remove();
  const W = document.getElementById('graph-svg').clientWidth;
  const H = document.getElementById('graph-svg').clientHeight;
  const g = svg.append('g');
  svg.call(d3.zoom().scaleExtent([0.3, 4]).on('zoom', e => g.attr('transform', e.transform)));

  const root = d3.pack().size([W - 20, H - 20]).padding(8)(
    d3.hierarchy({ children: data.communities }).sum(d => d.size || 1)
  );

  const bubble = g.selectAll('g').data(root.children || []).enter().append('g')
    .attr('class', 'comm-bubble')
    .attr('transform', d => `translate(${d.x + 10},${d.y + 10})`)
    .on('click', (event, d) => openCommunity(d.data.id));

  bubble.append('circle').attr('r', d => d.r)
    .attr('fill', d => d.data.color + '22').attr('stroke', d => d.data.color).attr('stroke-width', 2);

  bubble.append('text').text(d => d.data.label).attr('text-anchor', 'middle').attr('dy', -4)
    .attr('font-size', 11).attr('fill', d => d.data.color).attr('font-weight', 700);

  bubble.append('text').text(d => `${d.data.size} entities`).attr('text-anchor', 'middle').attr('dy', 11)
    .attr('font-size', 9).attr('fill', d => d.data.color);
}
```

- [ ] **Step 4: Update `setAppState('ready')` to call the new function**

In `app/static/app.js`, in `setAppState`, find the line:

```javascript
    document.getElementById('progress-box').style.display = 'none';
    loadGraph();
```

Replace `loadGraph();` with `loadGraphOverview();`.

- [ ] **Step 5: Commit**

```bash
git add app/static/app.js app/static/index.html app/static/style.css
git commit -m "feat(G3): render community overview as clickable bubbles"
```

---

### Task 6: Frontend — community drill-down and node-click expansion

**Files:**
- Modify: `app/static/app.js`

- [ ] **Step 1: Add `openCommunity`, `mergeIntoGraph`, `expandNode`, `loadMoreCommunity`**

In `app/static/app.js`, add these functions right after `renderOverview`:

```javascript
/**
 * Fetches a community's nodes/edges and renders them, replacing the overview.
 * @param {number} id - The community id to open.
 */
async function openCommunity(id) {
  const data = await (await fetch(`${API}/graph/community/${id}?limit=150`)).json();
  viewMode = 'detail';
  currentCommunityId = id;
  currentLimit = 150;
  graphData = { nodes: data.nodes, edges: data.edges };
  document.getElementById('graph-back-btn').style.display = 'inline-block';
  document.getElementById('load-more-btn').style.display = data.truncated ? 'inline-block' : 'none';
  renderGraph(graphData);
}

/**
 * Merges newly fetched nodes/edges into the currently rendered graph in place,
 * then re-renders. Nodes that already exist keep their D3-assigned x/y
 * (force simulations only randomize position for nodes missing x/y), so
 * already-visible nodes do not jump when new ones are added.
 * @param {Array} newNodes - Node objects to add (deduped by id).
 * @param {Array} newEdges - Edge objects to add (deduped by source-target pair).
 */
function mergeIntoGraph(newNodes, newEdges) {
  const existingIds = new Set(graphData.nodes.map(n => n.id));
  for (const n of newNodes) {
    if (!existingIds.has(n.id)) { graphData.nodes.push(n); existingIds.add(n.id); }
  }
  const edgeKey = e => `${e.source}->${e.target}`;
  const existingEdgeKeys = new Set(graphData.edges.map(edgeKey));
  for (const e of newEdges) {
    const k = edgeKey(e);
    if (!existingEdgeKeys.has(k)) { graphData.edges.push(e); existingEdgeKeys.add(k); }
  }
  renderGraph(graphData);
}

/**
 * Fetches a node's 1-hop neighbors and merges them into the current view.
 * @param {string} name - The node id to expand.
 */
async function expandNode(name) {
  const data = await (await fetch(`${API}/graph/node/${encodeURIComponent(name)}/neighbors?limit=40`)).json();
  mergeIntoGraph(data.nodes, data.edges);
}

/**
 * Re-fetches the current community at a higher limit and merges the result.
 * @returns {Promise<boolean>} Whether the community still has more nodes beyond the new limit.
 */
async function loadMoreCommunity() {
  currentLimit += 150;
  const data = await (await fetch(`${API}/graph/community/${currentCommunityId}?limit=${currentLimit}`)).json();
  mergeIntoGraph(data.nodes, data.edges);
  return data.truncated;
}
```

- [ ] **Step 2: Wire the back button and load-more button**

In `app/static/app.js`, add near the other top-level `document.getElementById(...).addEventListener` calls (e.g. right after the `reset-btn` listener):

```javascript
document.getElementById('graph-back-btn').addEventListener('click', () => {
  document.getElementById('load-more-btn').style.display = 'none';
  loadGraphOverview();
});

document.getElementById('load-more-btn').addEventListener('click', async () => {
  const truncated = await loadMoreCommunity();
  document.getElementById('load-more-btn').style.display = truncated ? 'inline-block' : 'none';
});
```

- [ ] **Step 3: Add the click-to-expand handler in `renderGraph`**

In `app/static/app.js`, inside `renderGraph`, find:

```javascript
  const tooltip = document.getElementById('graph-tooltip');
  node.on('mouseover', (event, d) => {
```

Add a new `.on('click', ...)` to the `node` selection right before this line:

```javascript
  node.on('click', (event, d) => expandNode(d.id));

  const tooltip = document.getElementById('graph-tooltip');
  node.on('mouseover', (event, d) => {
```

- [ ] **Step 4: Commit**

```bash
git add app/static/app.js
git commit -m "feat(G3): add community drill-down and click-to-expand neighbors"
```

---

### Task 7: Frontend — Q&A answer focuses the Graph tab, remove dead highlight code

**Files:**
- Modify: `app/static/app.js`

- [ ] **Step 1: Replace `lastSubgraphNodes`/`lastSubgraphEdges` declarations**

In `app/static/app.js`, find the top-of-file declarations:

```javascript
let lastSubgraphNodes = new Set();
let lastSubgraphEdges = new Set();
```

Replace with:

```javascript
let lastSubgraphNodes = [];
let lastSubgraphEdges = [];
```

- [ ] **Step 2: Remove `highlightSubgraph`, add `showFocusSubgraph`**

In `app/static/app.js`, delete the entire `highlightSubgraph` function and replace it with:

```javascript
/**
 * Renders the subgraph of the latest Q&A answer directly (no community
 * overview needed first) — the pipeline already caps this at <=150 nodes.
 * @param {string[]} nodeNames - Node ids from the query response.
 * @param {Array} edgeTuples - [source, relation, target] tuples from the query response.
 */
function showFocusSubgraph(nodeNames, edgeTuples) {
  const nodeSet = new Set(nodeNames);
  const nodes = nodeNames.map(id => ({
    id,
    community: 0,
    color: '#f59e0b',
    degree: edgeTuples.filter(e => e[0] === id || e[2] === id).length,
  }));
  const edges = edgeTuples
    .filter(e => nodeSet.has(e[0]) && nodeSet.has(e[2]))
    .map(e => ({ source: e[0], target: e[2], relation: e[1] }));
  viewMode = 'detail';
  currentCommunityId = null;
  graphData = { nodes, edges };
  document.getElementById('graph-back-btn').style.display = 'inline-block';
  document.getElementById('load-more-btn').style.display = 'none';
  renderGraph(graphData);
}
```

- [ ] **Step 3: Call it from `sendMessage`**

In `app/static/app.js`, in `sendMessage`, find:

```javascript
    const data = await r.json();
    updateMessage(typingId, data);
    highlightSubgraph(data.subgraph_nodes, data.subgraph_edges);
```

Replace with:

```javascript
    const data = await r.json();
    updateMessage(typingId, data);
    lastSubgraphNodes = data.subgraph_nodes;
    lastSubgraphEdges = data.subgraph_edges;
    showFocusSubgraph(lastSubgraphNodes, lastSubgraphEdges);
```

- [ ] **Step 4: Commit**

```bash
git add app/static/app.js
git commit -m "feat(G3): focus Graph tab on the latest Q&A answer's subgraph"
```

---

### Task 8: Manual verification

**Files:** none (verification only)

- [ ] **Step 1: Run the backend test suite**

Run: `pytest tests/ -v`
Expected: all tests pass, including the new graph/community/neighbors tests from Tasks 1-4.

- [ ] **Step 2: Start the app**

```bash
uvicorn app.main:app --reload --port 8000
```

- [ ] **Step 3: Build the `ai_history` demo dataset (small, fast) and check the overview**

In the browser at `http://localhost:8000`: select the dataset toggle, build the KG, open the "🕸 Knowledge Graph" tab. Confirm: a handful of labeled, sized bubbles appear (not a tangle of 30+ nodes), no lag.

- [ ] **Step 4: Check drill-down and expansion**

Click a bubble — confirm it opens into a readable node-link diagram of just that community. Click a node — confirm new neighbor nodes appear without the existing ones jumping to new positions. Click "← Overview" — confirm it returns to the bubble view.

- [ ] **Step 5: Check Q&A focus**

Ask a question in the Q&A tab, then switch to the Graph tab. Confirm it shows the answer's subgraph (amber nodes) directly rather than the bubble overview.

- [ ] **Step 6: Check the `hotpotqa` snapshot at scale (the original complaint)**

Switch to the HotpotQA dataset, build (or import `data/hotpotqa.graphrag` via the "⬆ Load snapshot" button), open the Graph tab. Confirm the overview renders instantly (it's just a few community bubbles) and stays responsive — this is the 30k-node case that used to lag.
