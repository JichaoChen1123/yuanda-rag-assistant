# 源答 · SaaS 知识助手：Plus 启动与演示

本文说明如何使用已有 ChatGPT 订阅运行 [yuanda-rag-assistant](https://github.com/JichaoChen1123/yuanda-rag-assistant)。

## 1. 准备 Python 环境

使用 Python 3.11，在仓库根目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.4.1 --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt "transformers==4.57.6"
```

本机实测组合为 torch 2.4.1+cpu、sentence-transformers 3.1.1、transformers 4.57.6、chromadb 0.5.5。上述命令保留现有依赖，并固定实测的 Transformers 版本；其他传递依赖仍未形成完整锁文件。

## 2. 登录官方 Codex CLI

安装官方 `@openai/codex` CLI，运行：

```powershell
codex login
codex login status
```

选择 ChatGPT 登录，状态应显示 `Logged in using ChatGPT`。接入方式依据 [OpenAI 官方认证文档](https://learn.chatgpt.com/docs/auth)。应用不自行读取、复制或发布认证文件，认证由官方 CLI 管理。

## 3. 创建 Plus 配置

首次配置时，在仓库根目录运行：

```powershell
Copy-Item .env.plus.example .env
```

已有 `.env` 时直接编辑该文件，避免覆盖原有本机配置。关键设置如下：

```dotenv
APP_NAME=源答 · SaaS 知识助手
LLM_PROVIDER=codex
LLM_FALLBACK_ORDER=["codex"]
CODEX_BINARY=codex
CODEX_MODEL=
CODEX_TIMEOUT=180
VECTOR_BACKEND=chroma
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DEVICE=cpu
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
ENABLE_RERANKING=true
```

保持 `LLM_FALLBACK_ORDER=["codex"]`。生成的实际路由由此列表决定，单独设置 `LLM_PROVIDER=codex` 不会关闭其他回退选项。

Windows 的 `CODEX_BINARY` 请填本机原生 `codex.exe` 的实际路径，不能使用 PowerShell 包装脚本。Linux/macOS 可使用可被进程找到的 `codex`。本地绝对路径只保存在 `.env` 中。

首次入库或检索时会下载两个公开模型：`BAAI/bge-small-en-v1.5` 用于 384 维向量，`cross-encoder/ms-marco-MiniLM-L-6-v2` 用于重排。它们在 CPU 本地计算，无需模型 API Key。也可将模型名替换为已下载的本地模型目录。首次下载需要网络；需要自定缓存位置时，在启动 Python 前设置 `HF_HOME` 和 `HF_HUB_CACHE`。

## 4. 启动后端与界面

在仓库根目录的第一个终端运行：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

第二个终端运行：

```powershell
$env:NO_PROXY='127.0.0.1,localhost,::1'
$env:API_URL='http://127.0.0.1:8000'
.\.venv\Scripts\python.exe -m streamlit run frontend/streamlit/app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true --browser.gatherUsageStats false
```

打开 [源答界面](http://127.0.0.1:8501/)，API 说明见 [Swagger 页面](http://127.0.0.1:8000/docs)。如果本机使用代理，请让 localhost 绕过代理；无需为没有代理的环境另配代理。CLI 适配器使用 certifi CA 包，不关闭证书验证。

保留的 Docker 配置未接入宿主机 Codex 登录与可执行文件，本次 Plus 演示没有验证 Docker 启动路线。

## 5. 导入文档并演示

在 Upload 页上传 `demo-documents/` 中的五个 `.txt` 文件。它们是明确标注的虚构 NimbusDesk 帮助文档，不能视为真实公司的政策。详见 [演示文档说明](demo-documents/README.md)。

| 场景 | 输入 | 检查点 |
|---|---|---|
| 角色权限 | `Who can manage billing? Can an Editor do it?` | Owner 可以、Editor 不可以；引用 `workspace-roles` |
| 错误排障 | `What does EXP-104 mean, and what should I do?` | 找到指定错误码与处理方式；引用 `export-troubleshooting` |
| 信息不足 | `What is the NimbusDesk refund amount and refund deadline?` | 文档无退款政策，应回答信息不足 |
| 结构化整理 | `Summarize document export permissions and export task states.`，选择 `Output=summary` | 返回结构化 `items` 和来源 |

2026-10-13 本地实测：5 份文档、5 个分块入库成功；以上 4 个输入通过原 HTTP 查询流程，向量与 BM25 均返回检索结果，RRF 完成融合，CrossEncoder 实际重排，生成 provider 为 `codex`。权限和错误码答案引用对应文档；退款问题返回信息不足；摘要返回 3 条结构化结果。Streamlit 页面另完成一次错误码查询并显示引用。

四次 HTTP 查询的服务端耗时约 20–32 秒，受账号与网络状态影响。这是小样本功能验证，不是生产准确率、稳定延迟或业务效果证明。

## 6. 无网络回归检查

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_codex_provider.py -q -p no:cacheprovider
```

本次 10 项 provider 回归测试通过。这组测试不会调用真实模型；端到端验证与回归测试是两类证据。

## 接入与能力边界

订阅适配器强制 ChatGPT 登录，移除子进程中的 OpenAI/Codex API Key，并拒绝未完成的 CLI 结果。订阅用量限制仍适用。每次查询使用独立临时 CLI 会话，没有实现多轮记忆。

结构化生成采用提示约束 + JSON 对象解析，没有使用原生严格 JSON Schema。CLI 适配器不执行现有接口的 `temperature`、`max_tokens` 采样参数。

界面的 confidence 是启发式分值，不是正确概率；评测的 citation correctness 只检查引用是否属于检索结果，不判断论断是否被证据支持。默认模型与实测题以英文为主，中文检索质量尚未验证。本项目没有 MCP、Function Calling、Dify/Coze 或模型训练能力。

运行文件位于 `.private/`，索引位于 `data/`，本机配置位于 `.env`，这些位置均已加入 Git 忽略。其他 provider 适配器仍保留，但不参与上述 Plus 配置与验证。
