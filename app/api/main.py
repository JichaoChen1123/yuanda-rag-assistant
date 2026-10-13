"""FastAPI application — the HTTP entrypoint to the RAG system.

Endpoints:
  GET  /health                    — liveness + index stats
  POST /api/v1/ingest             — ingest documents from configured paths
  POST /api/v1/query              — run a RAG query
  POST /api/v1/evaluate           — run the eval harness on a case file
  GET  /api/v1/documents          — list indexed documents (sources)
  DELETE /api/v1/index            — wipe the indices (admin)

The app is intentionally thin: it delegates to the modules under app/.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.evaluation.harness import evaluate, load_cases, save_report
from app.generation.pipeline import get_pipeline
from app.generation.providers import get_llm
from app.ingestion.pipeline import IngestionPipeline
from app.retrieval.bm25 import get_bm25
from app.retrieval.vector_store import get_vector_store
from app.schemas.models import (
    EvalSummary,
    IngestionRequest,
    IngestionResult,
    QueryRequest,
    QueryResponse,
)

setup_logging()
logger = get_logger(__name__)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="面向 SaaS 帮助文档的知识助手，支持混合检索、重排、来源引用与评测。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Lifecycle ----

@app.on_event("startup")
def _startup() -> None:
    logger.info(f"Starting {settings.app_name} v{settings.app_version} "
                f"env={settings.environment} backend={settings.vector_backend}")


# ---- Health ----

@app.get("/health")
def health() -> dict:
    vs = get_vector_store()
    bm25 = get_bm25()
    providers = {}
    for name in settings.llm_fallback_order:
        try:
            llm = get_llm()._get(name)
            providers[name] = {"available": llm.health() if name == "codex" else True,
                               "model": llm.model}
        except Exception as e:
            providers[name] = {"available": False, "error": str(e)}
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "vector_backend": settings.vector_backend,
        "vector_count": vs.count(),
        "bm25_count": bm25.count(),
        "providers": providers,
    }


# ---- Ingestion ----

@app.post("/api/v1/ingest", response_model=IngestionResult)
def ingest(req: IngestionRequest) -> IngestionResult:
    paths = req.paths or [str(settings.documents_dir)]
    pipeline = IngestionPipeline()
    return pipeline.ingest(paths=paths, rebuild=req.rebuild_index)


@app.post("/api/v1/upload", response_model=IngestionResult)
async def upload_documents(files: list[UploadFile] = File(...)) -> IngestionResult:
    """Upload one or more files; they are saved into the documents dir and ingested."""
    docs_dir = Path(settings.documents_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for f in files:
        target = docs_dir / Path(f.filename).name
        content = await f.read()
        target.write_bytes(content)
        saved.append(str(target))
    pipeline = IngestionPipeline()
    return pipeline.ingest(paths=saved)


# ---- Query ----

@app.post("/api/v1/query", response_model=QueryResponse)
def query(req: QueryRequest) -> QueryResponse:
    try:
        return get_pipeline().run(req)
    except Exception as e:
        logger.exception("Query failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---- Documents listing ----

@app.get("/api/v1/documents")
def list_documents() -> dict:
    """Return a summary of indexed sources (unique filenames)."""
    bm25 = get_bm25()
    metas = bm25._metadatas  # internal but useful here; could promote to public API
    by_source: dict[str, dict] = {}
    for m in metas:
        src = m.get("source", "unknown")
        info = by_source.setdefault(src, {
            "source": src,
            "doc_id": m.get("doc_id"),
            "doc_type": m.get("doc_type"),
            "chunks": 0,
        })
        info["chunks"] += 1
    return {"count": len(by_source), "documents": list(by_source.values())}


# ---- Evaluation ----

@app.post("/api/v1/evaluate", response_model=EvalSummary)
def run_evaluation(cases_path: str = "tests/eval_cases.yaml") -> EvalSummary:
    cases = load_cases(cases_path)
    summary = evaluate(cases)
    save_report(summary)
    return summary


# ---- Admin ----

@app.delete("/api/v1/index")
def wipe_index() -> dict:
    vs = get_vector_store()
    vs.delete_all()
    get_bm25().clear()
    return {"status": "cleared"}
