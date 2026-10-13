# 源答 · SaaS 知识助手

把 SaaS 帮助文档变成可以提问、查看来源的知识助手。适合演示产品规则查询、操作排障，以及从文档中整理摘要、决策、风险和行动项。

项目仓库：[JichaoChen1123/yuanda-rag-assistant](https://github.com/JichaoChen1123/yuanda-rag-assistant)。

## 产品功能

| 功能 | 使用方式 |
|---|---|
| 文档入库 | 上传 PDF、DOCX、TXT、Markdown 或 CSV，解析后分块并建立索引 |
| 规则问答 | 查询角色权限、导出规则等文档内容，查看回答关联的来源和片段 |
| 操作排障 | 结合语义检索与 BM25，查找问题描述和指定错误码 |
| 内容整理 | 选择 `summary`、`decisions`、`risks` 或 `actions`，查看解析后的条目与引用 |
| 检索检查 | 展开检索分块，查看来源、检索方式、排序和分数 |
| 评测 | 使用带参考信息的题集检查检索、引用、关键词约束和耗时，生成报告 |

仓库提供 Streamlit 和 React 两套界面。本次端到端演示使用 Streamlit；React 界面保留在仓库中，未完成同等范围的端到端验证。

## 实际技术栈

| 层次 | 本次演示使用的实现 |
|---|---|
| 后端 | Python 3.11、FastAPI、Pydantic |
| 文档处理 | pypdf、python-docx、tiktoken，以及项目加载与分块模块 |
| 文档向量 | sentence-transformers；`BAAI/bge-small-en-v1.5`，384 维，CPU 计算 |
| 向量存储 | Chroma 本地持久化 |
| 混合检索 | `rank-bm25` 关键词检索 + 向量检索，使用加权 RRF 合并排序 |
| 重排 | CrossEncoder；Plus 演示配置使用 `cross-encoder/ms-marco-MiniLM-L-6-v2`，CPU 计算 |
| 答案生成 | 官方 Codex CLI，复用已登录的 ChatGPT 订阅 |
| 演示界面 | Streamlit；另保留 React + TypeScript + Vite 界面 |
| 评测与回归 | 现有评测框架、pytest、订阅适配器回归测试 |

Qdrant、Ollama、OpenAI API 和 Anthropic API 适配器仍保留。它们未参与本次 Plus 演示；本次运行不需要购买模型 API 额度。

## 保留的 RAG 流水线

入库流程：文档加载 → 带重叠的分块 → 本地 embedding → 写入 Chroma，并建立 BM25 索引。

查询流程：

1. 对问题生成向量，分别执行向量检索和 BM25 检索。
2. 用加权 Reciprocal Rank Fusion（RRF）合并候选结果。
3. 用 CrossEncoder 对问题与候选片段联合打分，选出生成所需的分块。
4. 将问题、分块和引用要求组成提示，交给 ChatGPT 订阅生成答案。
5. 提取属于检索结果的引用；结构化任务解析 JSON 对象并展示条目。
6. 返回回答、引用、分块、耗时、provider 和启发式 confidence 分值。

检索、重排和生成由固定流程组织；本项目没有实现让模型自主选择工具的 Agent。

## 使用 ChatGPT Plus 启动

```powershell
git clone https://github.com/JichaoChen1123/yuanda-rag-assistant.git
cd yuanda-rag-assistant
```

按 [Plus 安装、配置与演示说明](RUN_PLUS.md) 建立 Python 环境、登录官方 Codex CLI，并从 `.env.plus.example` 创建 `.env`。

必须保持 `LLM_FALLBACK_ORDER=["codex"]`，这样生成失败时不会回退到 API 或本地大语言模型。实际路由以此列表为准，单独设置 `LLM_PROVIDER=codex` 不足以限制 provider。

在仓库根目录的两个终端中分别启动：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

```powershell
$env:NO_PROXY='127.0.0.1,localhost,::1'
$env:API_URL='http://127.0.0.1:8000'
.\.venv\Scripts\python.exe -m streamlit run frontend/streamlit/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

打开 [知识助手界面](http://127.0.0.1:8501/)，在 Upload 页上传 `demo-documents/` 中的五个 `.txt` 文件。API 说明见 [Swagger 页面](http://127.0.0.1:8000/docs)。

现有 Docker 配置未配置宿主机 Codex 登录与可执行文件的挂载，也未完成本次 Plus 路线验证。Plus 演示使用上述本机启动方式。

## 已完成的验证

2026-10-13，本地入库 5 份虚构帮助文档，共生成 5 个分块。通过原 HTTP 查询流程完成以下 4 个场景，生成 provider 均为 `codex`；向量检索、BM25、RRF 和 CrossEncoder 均实际执行。

| 场景 | 实际输入 | 检查结果 |
|---|---|---|
| 角色权限 | `Who can manage billing? Can an Editor do it?` | 回答 Owner 可以、Editor 不可以，并引用角色文档 |
| 指定错误码 | `What does EXP-104 mean, and what should I do?` | 找到对应错误及处理方式，并引用排障文档 |
| 文档范围外问题 | `What is the NimbusDesk refund amount and refund deadline?` | 文档没有退款政策，回答信息不足 |
| 结构化摘要 | `Summarize document export permissions and export task states.`，`output_type=summary` | 返回 3 条结构化结果及来源 |

Streamlit 页面另完成一次错误码查询并显示引用。上述 4 次 HTTP 查询的服务端耗时约 20–32 秒，受账号和网络状态影响；这些结果是小样本功能验证，不代表生产准确率、稳定耗时或业务收益。

订阅适配器另有 10 项无需联网的回归测试，覆盖 provider 限制、API Key 环境清理、ChatGPT 登录检查、完成事件、JSON 对象解析与错误脱敏：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_codex_provider.py -q -p no:cacheprovider
```

## API 与评测入口

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/health` | 查看服务、索引数量和 provider 状态 |
| POST | `/api/v1/ingest` | 从配置目录或指定路径入库 |
| POST | `/api/v1/upload` | 上传文件并入库 |
| POST | `/api/v1/query` | 问答或结构化整理 |
| GET | `/api/v1/documents` | 查看已入库来源 |
| POST | `/api/v1/evaluate` | 按 `cases_path` 运行题集 |
| DELETE | `/api/v1/index` | 清空向量与 BM25 索引 |

查询示例：

```powershell
$payload = @{
  query = 'What does EXP-104 mean, and what should I do?'
  output_type = 'answer'
  top_k = 5
  enable_reranking = $true
  llm_provider = 'codex'
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/v1/query' -ContentType 'application/json' -Body $payload
```

`output_type` 支持 `answer`、`summary`、`decisions`、`risks`、`actions`。评测题格式可参考 `tests/eval_cases.yaml`，命令行入口为：

```powershell
.\.venv\Scripts\python.exe scripts/run_eval.py tests/eval_cases.yaml
```

评测会调用实际生成 provider，消耗订阅用量。报告写入 `benchmark_results/`。内置 grounding、hallucination 和 citation correctness 指标采用规则与引用标记检查，不等同于人工事实核验。

## 范围与限制

- 结构化输出使用提示约束 + JSON 对象解析，没有启用原生严格 JSON Schema；业务字段仍可能需要进一步校验。
- 引用检查确认来源属于检索结果，不保证每一项论断都被该来源支持；confidence 是启发式分值，不是正确概率。
- 默认 embedding 和演示题以英文为主，中文界面不代表中文检索效果已验证。
- 每次查询使用独立临时 CLI 会话，没有实现多轮对话记忆。
- 本次验收使用本地单人环境、英文帮助文档、Streamlit、Chroma 和 ChatGPT 订阅；其他前端与后端组合可分别验证。
- `.env`、`.private/` 和 `data/` 是本机配置、运行文件与索引位置，已加入 Git 忽略，不应发布。

<details>
<summary>开源说明</summary>

本项目基于 [PiriTnz/enterprise-rag-system](https://github.com/PiriTnz/enterprise-rag-system)，保留原 RAG 流水线和 [MIT 许可证](LICENSE)，增加官方 Codex CLI 的 ChatGPT 订阅接入、虚构 SaaS 演示文档和界面接线修复。

原作者 [PiriTnz](https://github.com/PiriTnz) 提供的 [enterprise-rag-system](https://github.com/PiriTnz/enterprise-rag-system) 包含文档处理、分块、embedding、向量存储、BM25、RRF、CrossEncoder、引用、评测框架及两套前端。

本仓库在此基础上增加 ChatGPT 订阅生成适配器、Plus 配置与说明、虚构演示文档、provider 回归测试，以及必要的界面接线和中文品牌调整。具体改动见提交历史。

项目沿用 [MIT 许可证](LICENSE)，保留原作者的版权声明。

</details>
