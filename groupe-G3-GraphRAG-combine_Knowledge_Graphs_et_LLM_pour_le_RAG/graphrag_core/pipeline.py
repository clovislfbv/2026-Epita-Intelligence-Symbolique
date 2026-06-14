"""Pipeline orchestrator for the GraphRAG system.

This module ties together entity detection, subgraph extraction, context
serialisation, and LLM completion into a single ``run`` function that accepts
a natural-language question and returns a :class:`PipelineResult`.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from .llm import LLMClient
from .graph import KnowledgeGraph
from .retriever import TraceStep, detect_entities, extract_subgraph, subgraph_to_context


@dataclass
class DocReference:
    """A reference to a source document that contributed to the answer.

    Attributes:
        filename: The name or path of the referenced file.
        pages: Optional list of relevant page numbers within the document.
        sections: Optional list of relevant section names within the document.
    """

    filename: str
    pages: Optional[List[int]] = None
    sections: Optional[List[str]] = None


@dataclass
class PipelineResult:
    """The complete output of a single pipeline run.

    Attributes:
        answer: The natural-language answer produced by the LLM.
        trace: Ordered list of TraceStep records describing each BFS hop.
        docs_used: List of DocReference instances for documents whose text
            overlapped with the retrieved subgraph nodes.
        subgraph_nodes: All node names included in the retrieved subgraph.
        subgraph_edges: All edges (as ``(src, relation, tgt)`` tuples)
            included in the retrieved subgraph.
    """

    answer: str
    trace: List[TraceStep]
    docs_used: List[DocReference]
    subgraph_nodes: List[str]
    subgraph_edges: List[tuple]


_PROMPT = """You are a precise Q&A assistant. Answer the question using ONLY the knowledge graph context below.

Rules:
- Give a SHORT, DIRECT answer — one phrase or one sentence maximum.
- Do NOT start with "Based on the context", "According to the knowledge graph", etc.
- Do NOT use markdown (no bold, no bullets, no headers).
- If the context is insufficient, say only: "I don't have enough information to answer this."

Context:
{context}

Question: {question}

Answer:"""


def run(
    question: str,
    kg: KnowledgeGraph,
    llm: LLMClient,
    docs_map: Optional[Dict[str, str]] = None,
    max_hops: int = 2,
    max_nodes: int = 150,
    history: Optional[List[Dict[str, str]]] = None,
) -> PipelineResult:
    """Execute the full GraphRAG pipeline for a single question.

    The function performs the following steps in order:

    1. **Entity detection** — scan the question for KG node names.
    2. **Subgraph extraction** — BFS up to *max_hops* hops from the seeds,
       capped at *max_nodes* nodes.  If no seeds are found the subgraph is
       empty and the LLM will report insufficient context.
    3. **Context serialisation** — convert the subgraph to a prompt snippet.
    4. **LLM completion** — call the LLM with the context, question, and any
       prior conversation history.
    5. **Doc matching** — mark any document whose text contains a subgraph node.
    6. **Result assembly** — package everything into a PipelineResult.

    Args:
        question: The natural-language question to answer.
        kg: The KnowledgeGraph to retrieve context from.
        llm: An LLMClient whose ``complete`` method accepts a prompt string and
            returns the generated answer string.
        docs_map: Optional mapping of filename to document text used to
            populate ``PipelineResult.docs_used``.  Defaults to ``None``.
        max_hops: Maximum BFS depth when extracting the subgraph.
            Defaults to 2.
        max_nodes: Hard cap on the number of nodes in the retrieved subgraph.
            Prevents BFS from exploding on high-degree hub nodes.  Defaults
            to 150.
        history: Optional prior conversation turns as a list of dicts with
            ``"role"`` and ``"content"`` keys, ordered oldest-first.  Passed
            directly to the LLM so it can reference earlier exchanges.

    Returns:
        A PipelineResult containing the answer, BFS trace, matched documents,
        and the nodes/edges of the retrieved subgraph.

    Raises:
        ValueError: If *question* is an empty string.
    """
    seeds = detect_entities(question, kg)
    subgraph = extract_subgraph(kg, seeds, max_hops=max_hops, max_nodes=max_nodes)
    context = subgraph_to_context(subgraph)
    answer = llm.complete(_PROMPT.format(context=context, question=question), history=history)

    docs_used: List[DocReference] = []
    if docs_map:
        for fname, text in docs_map.items():
            if any(n.lower() in text.lower() for n in subgraph.nodes):
                docs_used.append(DocReference(filename=fname))

    return PipelineResult(
        answer=answer,
        trace=subgraph.trace,
        docs_used=docs_used,
        subgraph_nodes=subgraph.nodes,
        subgraph_edges=subgraph.edges,
    )
