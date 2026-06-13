"""Pydantic request and response models for the GraphRAG FastAPI backend."""

from pydantic import BaseModel
from typing import List, Optional, Any


class TraceStepSchema(BaseModel):
    """Schema for a single BFS hop in the retrieval trace.

    Attributes:
        hop: The hop index (0-based) in the BFS traversal.
        from_node: The source entity name at this hop.
        relation: The relation label connecting from_node to to_nodes.
        to_nodes: List of entity names reached from from_node via relation.
    """

    hop: int
    from_node: str
    relation: str
    to_nodes: List[str]


class DocReferenceSchema(BaseModel):
    """Schema for a reference to a source document used in an answer.

    Attributes:
        filename: The name or path of the source file.
        pages: Optional list of relevant page numbers within the document.
        sections: Optional list of relevant section names within the document.
    """

    filename: str
    pages: Optional[List[int]] = None
    sections: Optional[List[str]] = None


class HistoryMessage(BaseModel):
    """A single turn in the conversation history.

    Attributes:
        role: Either ``"user"`` or ``"assistant"``.
        content: The text content of this turn.
    """

    role: str
    content: str


class QueryRequest(BaseModel):
    """Request body for the /query endpoint.

    Attributes:
        question: The natural-language question to answer.
        max_hops: Maximum BFS depth for subgraph extraction. Defaults to 2.
        history: Prior conversation turns sent in order, oldest first.
            Each entry has ``role`` (``"user"`` or ``"assistant"``) and
            ``content``.  Defaults to an empty list (no prior context).
    """

    question: str
    max_hops: int = 2
    history: List[HistoryMessage] = []


class QueryResponse(BaseModel):
    """Response body returned by the /query endpoint.

    Attributes:
        answer: The natural-language answer produced by the LLM.
        trace: Ordered list of TraceStepSchema records describing each BFS hop.
        docs_used: List of DocReferenceSchema instances for matched documents.
        subgraph_nodes: All node names included in the retrieved subgraph.
        subgraph_edges: All edges as [source, relation, target] lists.
    """

    answer: str
    trace: List[TraceStepSchema]
    docs_used: List[DocReferenceSchema]
    subgraph_nodes: List[str]
    subgraph_edges: List[List[Any]]


class DatasetSelectRequest(BaseModel):
    """Request body for the /dataset/select endpoint.

    Attributes:
        dataset: The dataset identifier to activate. Must be one of
            ``"hotpotqa"`` or ``"custom"``.
    """

    dataset: str
