"""Streamlit UI for the Enterprise RAG system.

A pragmatic frontend for demos and internal teams. The React frontend
(under frontend/react) is the production-style alternative.
"""
from __future__ import annotations

import json
import os
from typing import Any

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")


st.set_page_config(
    page_title="Enterprise RAG",
    page_icon="📚",
    layout="wide",
)


# ---- helpers ----

def api_get(path: str) -> Any:
    with httpx.Client(timeout=60) as c:
        r = c.get(f"{API_URL}{path}")
        r.raise_for_status()
        return r.json()


def api_post(path: str, payload: dict | None = None, files=None, params=None) -> Any:
    with httpx.Client(timeout=300) as c:
        if files:
            r = c.post(f"{API_URL}{path}", files=files, params=params)
        else:
            r = c.post(f"{API_URL}{path}", json=payload or {}, params=params)
        r.raise_for_status()
        return r.json()


# ---- sidebar ----

with st.sidebar:
    st.title("📚 Enterprise RAG")
    st.caption("Hybrid retrieval + reranking + citations")

    try:
        health = api_get("/health")
        st.success(f"API: ok ({health['vector_backend']})")
        st.metric("Vector chunks", health["vector_count"])
        st.metric("BM25 chunks", health["bm25_count"])

        st.markdown("**Providers**")
        for name, info in health["providers"].items():
            icon = "🟢" if info["available"] else "⚪"
            st.write(f"{icon} `{name}` — {info.get('model', info.get('error', ''))[:40]}")
    except Exception as e:
        st.error(f"API unreachable: {e}")

    st.divider()
    st.markdown("**Index actions**")
    if st.button("Ingest from documents/"):
        with st.spinner("Ingesting…"):
            try:
                res = api_post("/api/v1/ingest", {"paths": [], "rebuild_index": False})
                st.success(f"{res['documents_processed']} docs, "
                           f"{res['chunks_created']} chunks, "
                           f"{res['duration_seconds']:.1f}s")
            except Exception as e:
                st.error(str(e))
    if st.button("⚠️ Wipe index"):
        with httpx.Client() as c:
            c.delete(f"{API_URL}/api/v1/index")
        st.warning("Index cleared")


# ---- main ----

tab_query, tab_upload, tab_docs, tab_eval = st.tabs(
    ["🔍 Query", "📤 Upload", "📁 Documents", "🧪 Evaluation"]
)


with tab_query:
    st.subheader("Ask your documents")

    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        query = st.text_input("Question", placeholder="e.g. What caused the Q3 capacity shortfall?")
    with col2:
        output_type = st.selectbox(
            "Output",
            ["answer", "summary", "decisions", "risks", "actions"],
        )
    with col3:
        top_k = st.number_input("top_k", 1, 20, 5)

    col_a, col_b = st.columns(2)
    with col_a:
        provider = st.selectbox("Provider override",
                                ["auto", "codex"])
    with col_b:
        rerank = st.checkbox("Enable reranking", value=True)

    if st.button("Run", type="primary") and query:
        with st.spinner("Retrieving + generating…"):
            payload = {
                "query": query,
                "output_type": output_type,
                "top_k": int(top_k),
                "enable_reranking": rerank,
                "include_chunks": True,
            }
            if provider != "auto":
                payload["llm_provider"] = provider
            try:
                resp = api_post("/api/v1/query", payload)
            except Exception as e:
                st.error(f"Query failed: {e}")
                resp = None

        if resp:
            colA, colB, colC, colD = st.columns(4)
            colA.metric("Confidence", f"{resp['confidence']:.2f}")
            colB.metric("Latency", f"{resp['latency_ms']:.0f} ms")
            colC.metric("Provider", resp["provider_used"])
            colD.metric("Citations", len(resp["citations"]))

            st.markdown("### Answer")
            st.markdown(resp["answer"])

            if resp.get("items"):
                st.markdown("### Items")
                for it in resp["items"]:
                    with st.expander(f"• {it['title']}"):
                        st.write(it["detail"])
                        for c in it["citations"]:
                            page = f" p.{c['page']}" if c.get("page") else ""
                            st.caption(f"📄 {c['source']}{page} — _{c['snippet']}_")

            if resp["citations"]:
                st.markdown("### Citations")
                for c in resp["citations"]:
                    page = f", page {c['page']}" if c.get("page") else ""
                    st.markdown(f"**{c['source']}**{page}  \n_score: {c['score']:.2f}_  \n> {c['snippet']}")

            with st.expander("🔬 Retrieved chunks (debug)"):
                for c in resp.get("chunks", []) or []:
                    md = c["chunk"]["metadata"]
                    st.caption(
                        f"#{c['rank']}  retriever={c['retriever']}  score={c['score']:.3f}  "
                        f"id={c['chunk']['chunk_id']}  src={md.get('source')}"
                    )
                    st.code(c["chunk"]["text"][:500])


with tab_upload:
    st.subheader("Upload documents")
    files = st.file_uploader(
        "Drop PDFs, DOCX, TXT, or CSV files",
        accept_multiple_files=True,
        type=["pdf", "docx", "txt", "md", "csv"],
    )
    if st.button("Upload & ingest") and files:
        with st.spinner(f"Uploading {len(files)} files…"):
            multipart = [("files", (f.name, f.getvalue(), f.type)) for f in files]
            res = api_post("/api/v1/upload", files=multipart)
        st.success(
            f"Ingested {res['documents_processed']} docs / "
            f"{res['chunks_created']} chunks in {res['duration_seconds']:.1f}s"
        )
        if res.get("failures"):
            st.warning(f"{len(res['failures'])} failures")
            st.json(res["failures"])


with tab_docs:
    st.subheader("Indexed documents")
    try:
        data = api_get("/api/v1/documents")
        if data["count"] == 0:
            st.info("No documents indexed yet.")
        else:
            st.dataframe(data["documents"], use_container_width=True)
    except Exception as e:
        st.error(str(e))


with tab_eval:
    st.subheader("Evaluation harness")
    cases_path = st.text_input("Eval cases file", "tests/eval_cases.yaml")
    if st.button("Run evaluation"):
        with st.spinner("Running…"):
            try:
                summary = api_post("/api/v1/evaluate", params={"cases_path": cases_path})
            except Exception as e:
                st.error(str(e))
                summary = None
        if summary:
            cols = st.columns(6)
            cols[0].metric("Passed", f"{summary['passed']}/{summary['total_cases']}")
            cols[1].metric("Precision", f"{summary['avg_retrieval_precision']:.2f}")
            cols[2].metric("Recall", f"{summary['avg_retrieval_recall']:.2f}")
            cols[3].metric("Grounding", f"{summary['avg_grounding']:.2f}")
            cols[4].metric("Hallu rate", f"{summary['hallucination_rate']:.2f}")
            cols[5].metric("Cite ✓", f"{summary['avg_citation_correctness']:.2f}")
            st.json(summary, expanded=False)
