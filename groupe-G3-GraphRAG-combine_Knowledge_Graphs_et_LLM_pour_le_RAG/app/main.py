"""FastAPI application for the GraphRAG demo.

This module defines all HTTP endpoints for uploading documents, building
the knowledge graph (with SSE progress streaming), querying via the
GraphRAG pipeline, and managing dataset selection.
"""

import io
import os
import json
import asyncio
import zipfile
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from graphrag_core.llm import get_llm_client
from graphrag_core.extractor import extract_triples
from graphrag_core.graph import build_knowledge_graph, graph_to_json
from graphrag_core.pipeline import run as pipeline_run
from app.models import (
    QueryRequest, QueryResponse, DatasetSelectRequest,
    TraceStepSchema, DocReferenceSchema,
)

app = FastAPI(title="GraphRAG Demo")

_BASE = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", _BASE.parent / "data"))
CUSTOM_DIR = DATA_DIR / "custom"
HOTPOTQA_DIR = DATA_DIR / "hotpotqa"
CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
HOTPOTQA_DIR.mkdir(parents=True, exist_ok=True)

state: dict = {"kg": None, "docs_map": {}, "active_dataset": "custom"}


@app.post("/upload")
async def upload_files(files: list[UploadFile] = File(...)):
    """Upload one or more documents to the custom dataset directory.

    Each uploaded file is written to CUSTOM_DIR, overwriting any existing
    file with the same name.

    Args:
        files: A list of UploadFile objects provided via multipart form data.

    Returns:
        A dict with key ``"saved"`` mapping to the list of saved filenames.
    """
    saved = []
    for f in files:
        dest = CUSTOM_DIR / f.filename
        dest.write_bytes(await f.read())
        saved.append(f.filename)
    return {"saved": saved}


@app.post("/reset")
async def reset_custom():
    """Delete all files in the custom dataset directory and clear the KG state.

    Removes every file under CUSTOM_DIR, then resets ``state["kg"]`` to
    ``None`` and ``state["docs_map"]`` to an empty dict.

    Returns:
        A dict ``{"status": "reset"}`` on success.
    """
    for f in CUSTOM_DIR.iterdir():
        f.unlink()
    state["kg"] = None
    state["docs_map"] = {}
    return {"status": "reset"}


def _sse(stage: str, progress: int, message: str) -> str:
    """Format a Server-Sent Events data frame.

    Args:
        stage: A short string identifying the current pipeline stage
            (e.g. ``"extraction"``, ``"done"``, ``"error"``).
        progress: Integer percentage (0–100) representing pipeline progress.
        message: Human-readable description of the current step.

    Returns:
        An SSE-formatted string starting with ``"data: "`` and ending with
        a double newline as required by the SSE protocol.
    """
    return f"data: {json.dumps({'stage': stage, 'progress': progress, 'message': message})}\n\n"


def _download_hotpotqa(output_dir: Path, num_samples: int = 50) -> None:
    """Download a subset of HotpotQA and write sample .txt files + qa_pairs.json.

    Runs synchronously — call via ``asyncio.to_thread`` from async context.

    Args:
        output_dir: Directory where sample_XXXX.txt and qa_pairs.json are written.
        num_samples: Number of validation samples to download.
    """
    from datasets import load_dataset
    ds = load_dataset("hotpotqa/hotpot_qa", "fullwiki", split="validation", streaming=True)
    samples = []
    for i, row in enumerate(ds):
        if i >= num_samples:
            break
        samples.append(row)
    for i, sample in enumerate(samples):
        parts = []
        for title, sentences in zip(sample["context"]["title"], sample["context"]["sentences"]):
            parts.append(f"# {title}\n" + " ".join(sentences))
        (output_dir / f"sample_{i:04d}.txt").write_text("\n\n".join(parts), encoding="utf-8")
    qa_pairs = [{"question": s["question"], "answer": s["answer"]} for s in samples]
    (output_dir / "qa_pairs.json").write_text(
        json.dumps(qa_pairs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def _build_gen() -> AsyncGenerator[str, None]:
    """Async generator that builds the knowledge graph and streams SSE progress.

    Reads all .txt files from the active dataset directory, extracts triples via
    the LLM, constructs the KnowledgeGraph, and stores it in ``state``.
    For HotpotQA, automatically downloads 50 samples if the directory is empty.
    Progress is emitted as SSE frames at each major stage.  If an exception
    occurs at any point an SSE error frame is emitted and the generator
    returns.

    Yields:
        SSE-formatted strings describing the current build stage and progress.
    """
    try:
        llm = get_llm_client()
        src = HOTPOTQA_DIR if state["active_dataset"] == "hotpotqa" else CUSTOM_DIR

        # Auto-download HotpotQA if selected but no .txt files present yet
        if state["active_dataset"] == "hotpotqa":
            txt_files = [f for f in src.iterdir() if f.suffix == ".txt"]
            if not txt_files:
                yield _sse("extraction", 0, "Téléchargement HotpotQA (50 exemples)…")
                await asyncio.sleep(0)
                await asyncio.to_thread(_download_hotpotqa, src, 50)
                yield _sse("extraction", 5, "HotpotQA téléchargé.")
                await asyncio.sleep(0)

        files = [f for f in src.iterdir() if f.is_file() and f.suffix == ".txt"]
        if not files:
            yield _sse("error", 0, "Aucun document trouvé.")
            return

        docs_map: dict = {}
        all_triples = []
        for i, f in enumerate(files):
            text = f.read_text(encoding="utf-8", errors="ignore")
            docs_map[f.name] = text
            yield _sse("extraction", int(i / len(files) * 40), f"Extraction : {f.name}")
            await asyncio.sleep(0)
            all_triples.extend(extract_triples(text, llm))

        yield _sse("extraction", 40, f"{len(all_triples)} triplets extraits")
        yield _sse("graph_build", 50, "Construction du graphe RDF…")
        await asyncio.sleep(0)
        yield _sse("community_detection", 70, "Détection de communautés (Leiden)…")
        await asyncio.sleep(0)
        kg = build_knowledge_graph(all_triples, docs_map)
        yield _sse("indexing", 90, "Indexation pour le retrieval…")
        await asyncio.sleep(0)
        state["kg"] = kg
        state["docs_map"] = docs_map
        s = graph_to_json(kg)["stats"]
        yield _sse(
            "done",
            100,
            f"KG prêt — {s['node_count']} entités, {s['edge_count']} relations, {s['community_count']} communautés",
        )
    except Exception as e:
        yield _sse("error", 0, str(e))


@app.get("/build")
async def build():
    """Trigger an incremental knowledge graph build with SSE progress streaming.

    Reads documents from the active dataset directory, extracts triples,
    constructs the KnowledgeGraph, and persists it in ``state``.  Progress
    is streamed to the client as Server-Sent Events.

    Returns:
        A StreamingResponse with media type ``text/event-stream`` that emits
        SSE frames for each pipeline stage until ``"done"`` or ``"error"``.
    """
    return StreamingResponse(_build_gen(), media_type="text/event-stream")


@app.get("/graph")
async def get_graph():
    """Return the serialised knowledge graph as JSON.

    Returns:
        A JSON-serialisable dict produced by ``graph_to_json`` containing
        ``nodes``, ``edges``, ``communities``, and ``stats``.

    Raises:
        HTTPException: 404 if the knowledge graph has not been built yet.
    """
    if state["kg"] is None:
        raise HTTPException(404, "KG non construit")
    return graph_to_json(state["kg"])


@app.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    """Answer a question using the GraphRAG pipeline.

    Runs entity detection, BFS subgraph extraction, context serialisation,
    and LLM completion, then returns a structured response.

    Args:
        req: The query request containing the question and max_hops.

    Returns:
        A QueryResponse with answer, trace, docs_used, and subgraph data.

    Raises:
        HTTPException: 400 if the knowledge graph has not been built yet.
    """
    if state["kg"] is None:
        raise HTTPException(400, "KG non construit")
    llm = get_llm_client()
    history = [{"role": m.role, "content": m.content} for m in req.history]
    r = pipeline_run(req.question, state["kg"], llm, state["docs_map"], req.max_hops, history)
    return QueryResponse(
        answer=r.answer,
        trace=[
            TraceStepSchema(
                hop=s.hop,
                from_node=s.from_node,
                relation=s.relation,
                to_nodes=s.to_nodes,
            )
            for s in r.trace
        ],
        docs_used=[
            DocReferenceSchema(
                filename=d.filename,
                pages=d.pages,
                sections=d.sections,
            )
            for d in r.docs_used
        ],
        subgraph_nodes=r.subgraph_nodes,
        subgraph_edges=[[e[0], e[1], e[2]] for e in r.subgraph_edges],
    )


@app.get("/datasets")
async def list_datasets():
    """List available datasets and their files.

    Returns:
        A dict with keys ``"active"`` (the currently selected dataset name)
        and ``"datasets"`` (a mapping of dataset name to a dict containing
        a ``"files"`` list of filenames present in that dataset directory).
    """
    return {
        "active": state["active_dataset"],
        "datasets": {
            "custom": {"files": [f.name for f in CUSTOM_DIR.iterdir() if f.is_file()]},
            "hotpotqa": {"files": [f.name for f in HOTPOTQA_DIR.iterdir() if f.suffix == ".txt"]},
        },
    }


@app.post("/dataset/select")
async def select_dataset(req: DatasetSelectRequest):
    """Switch the active dataset and reset the knowledge graph state.

    Clears the current KG so that a new ``/build`` call will use the
    newly selected dataset's documents.

    Args:
        req: The dataset selection request containing the dataset name.

    Returns:
        A dict ``{"active": <dataset_name>}`` confirming the selection.

    Raises:
        HTTPException: 400 if the requested dataset is not ``"hotpotqa"``
            or ``"custom"``.
    """
    if req.dataset not in ("hotpotqa", "custom"):
        raise HTTPException(400, "Dataset inconnu. Valeurs: hotpotqa | custom")
    state["active_dataset"] = req.dataset
    state["kg"] = None
    return {"active": req.dataset}


@app.get("/export")
async def export_kg():
    """Serialize the current KG state into a downloadable .graphrag ZIP file.

    The archive contains:
    - ``triples.json``: list of {subject, relation, object} dicts.
    - ``docs.json``: mapping of filename to document text.
    - ``meta.json``: graph statistics for display on import.

    Returns:
        A binary ZIP response with Content-Disposition set to trigger download.

    Raises:
        HTTPException: 400 if no KG has been built yet.
    """
    if state["kg"] is None:
        raise HTTPException(400, "KG non construit — construisez le graphe d'abord.")

    triples_data = [
        {"subject": u, "relation": d.get("relation", ""), "object": v}
        for u, v, d in state["kg"].nx_graph.edges(data=True)
    ]
    stats = graph_to_json(state["kg"])["stats"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("triples.json", json.dumps(triples_data, ensure_ascii=False, indent=2))
        zf.writestr("docs.json", json.dumps(state["docs_map"], ensure_ascii=False))
        zf.writestr("meta.json", json.dumps(stats))
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=demo.graphrag"},
    )


@app.post("/import")
async def import_kg(file: UploadFile = File(...)):
    """Restore a KG state from an uploaded .graphrag ZIP file.

    Reads triples and docs from the archive, rebuilds the KnowledgeGraph
    (no LLM calls needed), and stores it in ``state``.

    Args:
        file: The .graphrag ZIP file uploaded via multipart form data.

    Returns:
        A dict with ``"status": "ok"`` and ``"stats"`` from the rebuilt KG.

    Raises:
        HTTPException: 400 if the file is not a valid .graphrag archive.
    """
    content = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
            triples_data = json.loads(zf.read("triples.json"))
            docs_map = json.loads(zf.read("docs.json"))
    except (zipfile.BadZipFile, KeyError) as exc:
        raise HTTPException(400, f"Fichier .graphrag invalide : {exc}")

    from graphrag_core.extractor import Triple
    triples = [Triple(t["subject"], t["relation"], t["object"]) for t in triples_data]
    kg = build_knowledge_graph(triples, docs_map)

    state["kg"] = kg
    state["docs_map"] = docs_map

    return {"status": "ok", "stats": graph_to_json(kg)["stats"], "docs": list(docs_map.keys())}


app.mount("/", StaticFiles(directory=_BASE / "static", html=True), name="static")
