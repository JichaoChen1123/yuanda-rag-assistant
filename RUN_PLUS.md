# 使用现有 ChatGPT 订阅运行

本仓库基于 [PiriTnz/enterprise-rag-system](https://github.com/PiriTnz/enterprise-rag-system)，保留原项目、历史和 MIT 许可证。此 Fork 增加官方 Codex CLI 订阅接入、本地演示文档，以及两个界面接线修复。分块、向量检索、BM25、RRF、CrossEncoder、引用和评测框架均来自原项目。

## 安装与连接

1. 使用 Python 3.11 建立 `.venv`，安装 `requirements.txt`。本机实测版本：torch 2.4.1+cpu、sentence-transformers 3.1.1、transformers 4.57.6、chromadb 0.5.5。CPU 环境可先从 PyTorch 官方 CPU wheel 源安装对应 torch，再安装原依赖。
2. 安装官方 `@openai/codex` CLI，运行 `codex login`，选择 ChatGPT 登录。`codex login status` 应显示 `Logged in using ChatGPT`。接入方式依据 [OpenAI 官方认证文档](https://learn.chatgpt.com/docs/auth)。
3. 复制 `.env.plus.example` 为 `.env`。保持 `LLM_FALLBACK_ORDER=["codex"]`，这样不会回退到其他模型服务。Windows 的 `CODEX_BINARY` 必须指向原生 `codex.exe`，不能是 PowerShell 包装脚本。通过 npm 全局安装时通常在 `%APPDATA%/npm/node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe`；请以实际安装位置为准。
4. 首次启动将下载两个公开模型：`BAAI/bge-small-en-v1.5`（384 维向量）和 `cross-encoder/ms-marco-MiniLM-L-6-v2`（重排）。也可以把 `.env` 中模型名替换为已下载的绝对本地目录。它们在 CPU 本地计算，无需模型 API Key。

分别在两个终端、仓库根目录运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

```powershell
$env:NO_PROXY='127.0.0.1,localhost,::1'
$env:API_URL='http://127.0.0.1:8000'
.\.venv\Scripts\python.exe -m streamlit run frontend/streamlit/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

打开 <http://127.0.0.1:8501/>。API 文档为 <http://127.0.0.1:8000/docs>。如本机已有代理，请让 localhost 绕过代理；没有代理时无需添加代理配置。CLI 适配器使用公开 certifi CA 包，不关闭证书验证。

## 演示

在 Upload 页上传 `demo-documents/` 中五个 `.txt` 文件。它们是明确标注的虚构 NimbusDesk 帮助文档。

| 输入 | 检查点 |
|---|---|
| Who can manage billing? Can an Editor do it? | Owner 可以、Editor 不可以；引用 workspace-roles |
| What does EXP-104 mean, and what should I do? | 找到指定错误码；引用 export-troubleshooting |
| What is the NimbusDesk refund amount and refund deadline? | 文档无此政策，回答信息不足 |
| Summarize document export permissions and export task states.（Output=summary） | 返回结构化 items 和来源 |

2026-10-13 本地实测：5 文档、5 分块入库成功，以上四个输入通过原 HTTP 查询流程；向量与 BM25 均有检索结果、CrossEncoder 实际重排、生成 provider 为 codex。权限与错误码答案引用对应文档；退款问题返回信息不足；summary 返回 3 条结构化结果。这是小样本功能验证，不是生产准确率。四次服务端耗时约 20–32 秒，与账号和网络有关。Streamlit 页面另完成一次错误码查询并显示引用。

## 接入边界

订阅适配器强制 ChatGPT 登录，移除子进程中的 OpenAI/Codex API Key，不读取或复制认证文件。订阅用量限制仍适用。每次 RAG 查询使用独立临时 CLI 会话；知识检索与会话记忆不是一回事。

结构化生成采用提示约束 + JSON 对象解析，不能称为原生严格 JSON Schema。CLI 不接受此接口的 temperature/max_tokens 采样参数，因此没有假装传入这些参数。界面的 confidence 是上游启发式分值，不是正确概率；评测中的 citation correctness 只检查引用是否属于检索结果，不判断论断是否被证据支持。

运行文件在 `.private/`、索引在 `data/`、本机配置在 `.env`，均已忽略。不要提交这些目录。原上游 README 的默认 Ollama/API 路线仍可查阅；本次演示使用上述 Plus 配置。

无网络回归检查：`python -m pytest tests/test_codex_provider.py -q -p no:cacheprovider`，本次 10 项通过。
