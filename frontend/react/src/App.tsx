import { useEffect, useState } from "react";
import { QueryPanel } from "./components/QueryPanel";
import { Sidebar } from "./components/Sidebar";
import { AnswerView } from "./components/AnswerView";
import type { Health, QueryResponse } from "./types";
import { getHealth } from "./api";

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getHealth().then(setHealth).catch(() => setHealth(null));
  }, []);

  return (
    <div className="app">
      <Sidebar health={health} />
      <main className="main">
        <header className="topbar">
          <h1>源答 · SaaS 知识助手</h1>
          <span className="subtitle">
            查询产品规则与操作指引，查看回答来源
          </span>
        </header>

        <QueryPanel
          onResult={setResponse}
          loading={loading}
          setLoading={setLoading}
        />
        <AnswerView response={response} loading={loading} />
      </main>
    </div>
  );
}
