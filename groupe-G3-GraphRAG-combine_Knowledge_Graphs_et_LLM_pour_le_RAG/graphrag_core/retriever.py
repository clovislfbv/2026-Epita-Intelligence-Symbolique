"""Multi-hop BFS retriever for the GraphRAG pipeline.

This module exposes three public functions:

* ``detect_entities`` — surface entity names from a natural-language question
  by matching against KnowledgeGraph node names.
* ``extract_subgraph`` — perform a breadth-first traversal from seed entities
  up to *max_hops* hops and collect the resulting nodes, edges, and trace.
* ``subgraph_to_context`` — serialise a SubgraphResult to a human-readable
  string suitable for inclusion in an LLM prompt.
"""

from dataclasses import dataclass, field
from typing import List, Set

from .graph import KnowledgeGraph

try:
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS as _SKL_STOPS
except ImportError:
    print("[retriever] sklearn not found — falling back to empty stopword base. Install scikit-learn for better entity filtering.")
    _SKL_STOPS = frozenset()

_ENTITY_STOPWORDS: frozenset = frozenset(_SKL_STOPS) | frozenset({
    # media / entertainment
    "film", "films", "movie", "series", "show",
    "director", "producer", "writer", "actor", "actress",
    "album", "debut", "song", "band", "comedy", "drama",
    "debut album", "debut single",
    # places / institutions
    "government", "country", "city", "town", "school", "university",
    "organization", "organisation", "institution", "company", "corporation",
    # nationality adjectives (single and compound)
    "american", "english", "french", "german", "british", "korean", "chinese",
    "south korean", "north korean", "latin american", "australian", "japanese",
    # generic occupations / roles
    "consultant", "consultants", "politician", "politicians",
    "celebrity", "celebrities", "author", "novelist",
    "member", "members", "leader", "leaders",
    # generic common nouns observed as spurious seeds
    "neighborhood", "neighborhoods", "neighbourhood", "neighbourhoods",
})


@dataclass
class TraceStep:
    """One hop step recorded during BFS traversal.

    Attributes:
        hop: The 1-based hop number at which this step occurred.
        from_node: Comma-separated list of frontier node names that were
            expanded during this hop.
        relation: A descriptive label for the traversal step; always
            ``"(traversal)"`` for BFS steps.
        to_nodes: Sorted list of newly discovered node names reached in
            this hop.
    """

    hop: int
    from_node: str
    relation: str
    to_nodes: List[str]


@dataclass
class SubgraphResult:
    """The result of a multi-hop BFS subgraph extraction.

    Attributes:
        nodes: All node names reachable from the seed entities within
            ``max_hops`` hops (includes the seeds themselves).
        edges: List of ``(from_node, relation, to_node)`` tuples representing
            every edge encountered during traversal (de-duplicated,
            insertion-ordered).
        trace: Ordered list of TraceStep records, one per hop that produced
            at least one new node.
    """

    nodes: List[str]
    edges: List[tuple]
    trace: List[TraceStep] = field(default_factory=list)


_HUB_DEGREE_THRESHOLD: int = 50


def detect_entities(question: str, kg: KnowledgeGraph) -> List[str]:
    """Detect entity names from a question by matching against KG node names.

    Matching is case-insensitive and requires whole-word boundaries, so short
    tokens like "it" or "he" do not spuriously match inside longer words.
    Nodes shorter than 4 characters, in the stopword list, or with degree
    above _HUB_DEGREE_THRESHOLD (generic hub nodes like "American") are skipped.

    Args:
        question: The natural language question to scan.
        kg: The KnowledgeGraph whose node names are matched against.

    Returns:
        A list of node names (preserving original casing) found as whole-word
        matches in the question, longest matches first to prefer specific
        entities over shorter ones.
    """
    import re
    q = question.lower()
    matches = [
        n for n in kg.nx_graph.nodes()
        if len(n) >= 4
        and n.lower() not in _ENTITY_STOPWORDS
        and kg.nx_graph.degree(n) <= _HUB_DEGREE_THRESHOLD
        and re.search(r'\b' + re.escape(n.lower()) + r'\b', q)
    ]
    return sorted(matches, key=len, reverse=True)


def extract_subgraph(
    kg: KnowledgeGraph,
    seed_entities: List[str],
    max_hops: int = 2,
    max_nodes: int = 150,
) -> SubgraphResult:
    """Extract a subgraph by BFS from seed entities up to *max_hops* hops.

    Both outgoing and incoming edges of each frontier node are traversed at
    every hop so that the returned subgraph is undirected in scope even
    though the underlying NetworkX graph is directed.

    Duplicate edges are removed while preserving insertion order.

    Args:
        kg: The KnowledgeGraph to traverse.
        seed_entities: Node names to start the BFS from.  Nodes absent from
            the graph are silently skipped.
        max_hops: Maximum number of hops to traverse from the seeds.
            Defaults to 2.

    Returns:
        A SubgraphResult containing all visited nodes, all encountered edges,
        and a trace of each hop that discovered at least one new node.
    """
    G = kg.nx_graph
    visited: Set[str] = set(seed_entities)
    edges: List[tuple] = []
    trace: List[TraceStep] = []
    frontier: Set[str] = set(seed_entities)

    for hop in range(1, max_hops + 1):
        next_frontier: Set[str] = set()
        for node in frontier:
            if node not in G:
                continue
            if len(visited) >= max_nodes:
                continue
            for _, nbr, data in G.out_edges(node, data=True):
                edges.append((node, data.get("relation", ""), nbr))
                if nbr not in visited and len(visited) < max_nodes:
                    visited.add(nbr)
                    if G.degree(nbr) <= _HUB_DEGREE_THRESHOLD:
                        next_frontier.add(nbr)
            for pred, _, data in G.in_edges(node, data=True):
                edges.append((pred, data.get("relation", ""), node))
                if pred not in visited and len(visited) < max_nodes:
                    visited.add(pred)
                    if G.degree(pred) <= _HUB_DEGREE_THRESHOLD:
                        next_frontier.add(pred)
        if next_frontier:
            trace.append(
                TraceStep(
                    hop=hop,
                    from_node=", ".join(sorted(frontier)),
                    relation="(traversal)",
                    to_nodes=sorted(next_frontier),
                )
            )
        frontier = next_frontier
        if not frontier:
            break

    unique_edges = list(dict.fromkeys(edges))
    return SubgraphResult(nodes=list(visited), edges=unique_edges, trace=trace)


def subgraph_to_context(result: SubgraphResult) -> str:
    """Serialise a SubgraphResult to a human-readable context string.

    Each edge is rendered on its own line as::

        src --[RELATION]--> tgt

    prefixed by a header line ``"Knowledge Graph context:"``.

    Args:
        result: The SubgraphResult produced by :func:`extract_subgraph`.

    Returns:
        A multi-line string suitable for inclusion in an LLM prompt.
    """
    lines = ["Knowledge Graph context:"]
    for src, rel, tgt in result.edges:
        lines.append(f"  {src} --[{rel}]--> {tgt}")
    return "\n".join(lines)
