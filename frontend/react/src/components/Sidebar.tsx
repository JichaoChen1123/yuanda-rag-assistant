import { ingest } from "../api";
import type { Health } from "../types";

export function Sidebar({ health }: { health: Health | null }) {
  const handleIngest = async () => {
    const res = await ingest(false);
    alert(`Ingested ${res.documents_processed} docs / ${res.chunks_created} chunks`);
  };

  return (
    <aside className="sidebar">
      <div className="brand">📚 源答 · SaaS 知识助手</div>
      <div className="status">
        {health ? (
          <>
            <div className={`status-dot ok`} /> API ready
            <div className="stat">
              <span>Backend</span><b>{health.vector_backend}</b>
            </div>
            <div className="stat">
              <span>Vector chunks</span><b>{health.vector_count}</b>
            </div>
            <div className="stat">
              <span>BM25 chunks</span><b>{health.bm25_count}</b>
            </div>
            <div className="providers">
              <div className="label">Providers</div>
              {Object.entries(health.providers).map(([name, info]) => (
                <div key={name} className={`provider ${info.available ? "on" : "off"}`}>
                  <span>{info.available ? "🟢" : "⚪"}</span>
                  <code>{name}</code>
                  <small>{info.model || ""}</small>
                </div>
              ))}
            </div>
          </>
        ) : (
          <><div className="status-dot off" /> API offline</>
        )}
      </div>
      <button className="btn" onClick={handleIngest}>Ingest documents/</button>
    </aside>
  );
}
