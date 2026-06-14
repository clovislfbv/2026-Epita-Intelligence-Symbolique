import json
import re
import time
from dataclasses import dataclass, field
from typing import List, Tuple

from .llm import LLMClient

_PRONOUNS: frozenset = frozenset({
    "he", "she", "it", "they", "we", "i", "you",
    "his", "her", "its", "their", "him", "them", "this", "that",
})


@dataclass(frozen=True)
class Triple:
    """An immutable subject-relation-object knowledge graph triple.

    Attributes:
        subject: The entity that is the source of the relation.
        relation: The relation label, expected in UPPER_SNAKE_CASE.
        object: The entity that is the target of the relation.
    """

    subject: str
    relation: str
    object: str


@dataclass
class RejectionCounts:
    """Counts of triples rejected during extraction, broken down by reason."""

    empty_field: int = 0
    too_short: int = 0
    pronoun_subject: int = 0
    pronoun_object: int = 0
    duplicate: int = 0

    @property
    def total(self) -> int:
        return self.empty_field + self.too_short + self.pronoun_subject + self.pronoun_object + self.duplicate


@dataclass
class ChunkStats:
    """Extraction statistics for a single text chunk."""

    char_count: int
    raw_triples: int
    kept_triples: int
    rejections: RejectionCounts


@dataclass
class DocumentExtractionStats:
    """Aggregated extraction statistics for one source document."""

    filename: str
    chunks: List[ChunkStats] = field(default_factory=list)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def total_chars(self) -> int:
        return sum(c.char_count for c in self.chunks)

    @property
    def total_raw(self) -> int:
        return sum(c.raw_triples for c in self.chunks)

    @property
    def total_kept(self) -> int:
        return sum(c.kept_triples for c in self.chunks)

    @property
    def total_rejections(self) -> RejectionCounts:
        r = RejectionCounts()
        for c in self.chunks:
            r.empty_field      += c.rejections.empty_field
            r.too_short        += c.rejections.too_short
            r.pronoun_subject  += c.rejections.pronoun_subject
            r.pronoun_object   += c.rejections.pronoun_object
            r.duplicate        += c.rejections.duplicate
        return r


_PROMPT = """Extract ALL entities and relations from the text as a JSON array of triples.
Each triple: {{"subject": "...", "relation": "UPPER_SNAKE_CASE", "object": "..."}}.

Rules:
- ALWAYS resolve pronouns to their referent: if "he" refers to "Scott Derrickson", use "Scott Derrickson" as the subject, never "he", "she", or "they".
- Use the full proper name of each entity, not a generic pronoun or reference.

Prioritize capturing:
- Nationalities/citizenship: [Person] --NATIONALITY--> [Country or adjective]
- Occupations/professions: [Person] --OCCUPATION--> [Job title]
- Government or official positions: [Person] --HELD_POSITION--> [Position name]
- Birth/death dates and places: [Person] --BORN_IN--> [Year or Place]
- Locations: [Entity] --LOCATED_IN--> [Place]
- Directed/starred/wrote/composed/founded/formed relations
- Membership or affiliation to groups, organizations, institutions

Output ONLY valid JSON. No explanation.

Text:
{text}"""


def chunk_text(text: str, chunk_size: int = 4000, overlap_paragraphs: int = 1) -> List[str]:
    """Split text into chunks at paragraph boundaries.

    Consecutive paragraphs are grouped until adding the next one would exceed
    chunk_size. The last `overlap_paragraphs` paragraphs of each chunk are
    repeated at the start of the next chunk so that entity references that
    span a paragraph boundary are still resolved correctly.

    A single paragraph that exceeds chunk_size is sent as its own chunk
    without truncation.

    Args:
        text: The input text to split.
        chunk_size: Maximum number of characters per chunk.
        overlap_paragraphs: Number of trailing paragraphs carried over as
            context into the next chunk.

    Returns:
        A non-empty list of chunk strings.
    """
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else [""]

    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > chunk_size:
            if current:
                chunks.append("\n\n".join(current))
                current = current[-overlap_paragraphs:]
                current_len = sum(len(p) for p in current)
            chunks.append(para)
            continue
        if current and current_len + len(para) > chunk_size:
            chunks.append("\n\n".join(current))
            current = current[-overlap_paragraphs:]
            current_len = sum(len(p) for p in current)
        current.append(para)
        current_len += len(para)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def _call_llm_with_retry(chunk: str, llm: LLMClient, max_retries: int = 1) -> List[dict]:
    """Call the LLM and parse the JSON array, retrying once on a formatting failure.

    A retry (with 3-second pause) is triggered when the response contains no JSON
    array at all — indicating a transient error such as rate limiting or an empty
    reply.  An explicit empty array ``[]`` from the LLM is valid and returned
    immediately without retry.
    """
    for attempt in range(max_retries + 1):
        raw = llm.complete(_PROMPT.format(text=chunk))
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if not m:
            if attempt < max_retries:
                print(f"    [extractor] no JSON in response — retrying in 3s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(3.0)
            continue
        try:
            items = json.loads(m.group())
            if not items:
                print(f"    [extractor] LLM returned [] for chunk ({len(chunk)} chars) — not retrying")
            return items
        except json.JSONDecodeError:
            if attempt < max_retries:
                print(f"    [extractor] JSON decode error — retrying in 3s (attempt {attempt + 1}/{max_retries + 1})")
                time.sleep(3.0)
    return []


def extract_triples(text: str, llm: LLMClient) -> List[Triple]:
    """Extract knowledge graph triples from text using an LLM.

    The text is split into overlapping chunks via chunk_text.  Each chunk is
    sent to the LLM with a structured prompt that requests a JSON array of
    triples.  The raw response is searched for the first JSON array, which is
    then parsed.  Items that are missing any of the required fields
    (``subject``, ``relation``, ``object``) are silently skipped.  Duplicate
    triples across all chunks are collapsed so that each unique triple appears
    only once in the returned list.

    Args:
        text: The input text to extract triples from.
        llm: An LLMClient instance used to call the model.

    Returns:
        A deduplicated list of Triple instances extracted from the text,
        preserving first-occurrence order.
    """
    seen: set = set()
    result: List[Triple] = []
    for chunk in chunk_text(text):
        if not chunk.strip():
            continue
        items = _call_llm_with_retry(chunk, llm)
        for item in items:
            if not isinstance(item, dict):
                continue
            if not all(k in item for k in ("subject", "relation", "object")):
                continue
            subj = item["subject"].strip()
            rel  = item["relation"].strip().upper().replace(" ", "_")
            obj  = item["object"].strip()
            if not subj or not rel or not obj:
                continue
            if len(subj) < 2 or len(obj) < 2:
                continue
            if subj.lower() in _PRONOUNS or obj.lower() in _PRONOUNS:
                continue
            if len(obj) > 100:
                obj = obj[:100]
            t = Triple(subj, rel, obj)
            if t not in seen:
                seen.add(t)
                result.append(t)
    return result


def extract_triples_verbose(
    text: str, llm: LLMClient, filename: str = ""
) -> Tuple[List[Triple], DocumentExtractionStats]:
    """Like extract_triples but also collects per-chunk extraction statistics.

    Args:
        text: The input text to extract triples from.
        llm: An LLMClient instance used to call the model.
        filename: Optional document name stored in the returned stats object.

    Returns:
        A tuple ``(triples, stats)`` where ``triples`` is the same deduplicated
        list returned by :func:`extract_triples` and ``stats`` is a
        :class:`DocumentExtractionStats` describing what was kept, rejected,
        and why.
    """
    seen: set = set()
    result: List[Triple] = []
    doc_stats = DocumentExtractionStats(filename=filename)

    for chunk in chunk_text(text):
        if not chunk.strip():
            continue
        rejections = RejectionCounts()
        raw_count = 0
        kept_count = 0

        items = _call_llm_with_retry(chunk, llm)
        for item in items:
            raw_count += 1
            if not isinstance(item, dict) or not all(k in item for k in ("subject", "relation", "object")):
                rejections.empty_field += 1
                continue
            subj = item["subject"].strip()
            rel  = item["relation"].strip().upper().replace(" ", "_")
            obj  = item["object"].strip()
            if not subj or not rel or not obj:
                rejections.empty_field += 1
                continue
            if len(subj) < 2 or len(obj) < 2:
                rejections.too_short += 1
                continue
            if subj.lower() in _PRONOUNS:
                rejections.pronoun_subject += 1
                continue
            if obj.lower() in _PRONOUNS:
                rejections.pronoun_object += 1
                continue
            if len(obj) > 100:
                obj = obj[:100]
            t = Triple(subj, rel, obj)
            if t in seen:
                rejections.duplicate += 1
                continue
            seen.add(t)
            result.append(t)
            kept_count += 1

        doc_stats.chunks.append(ChunkStats(len(chunk), raw_count, kept_count, rejections))

    return result, doc_stats
