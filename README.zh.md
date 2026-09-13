# ChatCV 中文说明

把简历变成可对话的个人卡片。招聘方可以直接问经历、项目和技能，而不是只扫 PDF 条目。

本仓库默认用 **venv + uvicorn** 运行，不依赖 Docker。没有 API Key 时也可以启动首页和 `/health`；对话接口会返回明确的中文 JSON 错误。

## 环境要求

- Python 3.11+
- 约 2GB 内存即可（京东云等轻量 VPS 可用）
- 对话前需要 OpenAI 兼容的 LLM / Embedding 接口（官方 OpenAI，或 DeepSeek 等）

## 本地启动

```bash
git clone https://github.com/lucianwhy/ChatCV.git
cd ChatCV
cp .env.example .env
# 可以先不填 Key
./scripts/run.sh
```

浏览器打开 `http://localhost:8000`。健康检查：`http://localhost:8000/health`。

`scripts/run.sh` 会：创建 `.venv` → `pip install -r requirements.txt` → `uvicorn main:app --reload`。

手动等价命令：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 配置模型（稍后再做也可以）

编辑 `.env`：

```bash
# OpenAI 官方
OPENAI_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small

# DeepSeek 等 OpenAI 兼容接口
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.deepseek.com
# 或 LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
```

说明：

- `OPENAI_BASE_URL` 与 `LLM_BASE_URL` 等价，任填一个即可。
- DeepSeek 主要提供对话模型。若对方没有 Embedding 接口，请把 `EMBEDDING_BASE_URL` / `EMBEDDING_MODEL` 指到仍兼容 OpenAI Embeddings 的服务，再建向量库。
- 未配置 Key 时，`POST /chat`、`/summary`、`/job-match` 返回 HTTP 503，JSON 形如：

```json
{
  "error": true,
  "code": "llm_not_configured",
  "message": "尚未配置大模型 API。请在 .env 中设置 OPENAI_API_KEY；..."
}
```

## 换成你自己的简历

1. 把 PDF 放到 `data/`，例如替换 `data/CV_Demo.pdf`，或改 `config/base.yml` 里的 `data.cv_path`。
2. 按章节填写 `data/about_me.md`（简介 / 经历 / 项目 / 技能 / FAQ）。
3. 改 `config/base.yml` 的 `candidate`：姓名、一句话介绍、邮箱、LinkedIn、GitHub。
4. 替换 `static/default-avatar.png` 为头像。
5. 配置好 API Key 后构建向量库：

```bash
source .venv/bin/activate
./scripts/ingest.sh
# 或：python -m app.modules.rag_pipeline --ingest
```

首次对话时，若已有 Key 但还没有向量库，服务会尝试自动入库；失败时同样返回中文 503。

## 公开访问 / 邀请码

默认公开，无需登录。`.env` 里保持：

```bash
INVITE_CODES={}
```

若只想给特定招聘方：

```bash
INVITE_CODES={"ACME": {"company": "某公司", "recruiter": "张三", "active": true}}
```

## 部署到 VPS（非 Docker）

推荐目录：`/opt/ChatCV`。在本机改完并 `git push` 后，把代码同步上去（示例）：

```bash
rsync -av --exclude .venv --exclude data/vector_db --exclude logs \
  ./ root@你的服务器:/opt/ChatCV/
```

或打包拷贝：

```bash
tar czf chatcv.tar.gz --exclude .venv --exclude .git --exclude data/vector_db --exclude logs .
scp chatcv.tar.gz root@你的服务器:/tmp/
ssh root@你的服务器 'mkdir -p /opt/ChatCV && tar xzf /tmp/chatcv.tar.gz -C /opt/ChatCV'
```

服务器上：

```bash
cd /opt/ChatCV
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp -n .env.example .env
# 编辑 .env 填 Key；生产可设 ENVIRONMENT=production
# 生产建议去掉 --reload，省内存
uvicorn main:app --host 0.0.0.0 --port 8000
```

2GB 内存机器请不要同时开 Docker、Ollama 和多个 uvicorn reload 进程。

## 可选依赖（默认关闭）

以下包**不要**装也能启动。需要时再装：

```bash
pip install -r requirements-optional.txt
```

| 组件 | 作用 | 不装时 |
| --- | --- | --- |
| Guardrails | 额外内容安全 | 使用内置基础校验 |
| LangSmith | 调用追踪 | 普通日志 |
| MLflow | 实验记录 | 忽略 |
| Ollama / langchain-ollama | 本地模型 | 仅 OpenAI 兼容接口 |

Dockerfile / docker-compose 仍保留，仅作可选路径，不是默认运行方式。

## 常用接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 中文个人卡片 + 对话页 |
| GET | `/health` | 进程健康；附带 `llm_configured` / `vectorstore_ready` |
| POST | `/chat` | RAG 对话 |
| POST | `/summary` | 生成中文摘要 |
| POST | `/job-match` | 岗位匹配 |
| GET | `/auth/status` | 公开模式返回 `auth_enabled: false` |

开发环境还会开放 `/docs`。
