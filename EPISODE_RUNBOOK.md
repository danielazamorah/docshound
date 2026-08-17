# Agent Clinic Episode 3: DocsHound & Google Cloud Agent Runtime Runbook

This runbook contains the end-to-end guide, commands, architecture details, observability guides, and recording script for **Agent Clinic Episode 3** featuring **DocsHound** (a LangGraph-powered documentation gap agent) running on **Google Cloud Vertex AI Agent Runtime** with **Gemini 3.7 Flash**.

---

## 1. Episode Overview & Architecture

### Goal
Demonstrate how an autonomous software engineering agent built with **LangGraph** can find documentation gaps across repositories, generate high-fidelity documentation drafts using **Gemini 3.7 Flash**, deploy seamlessly to **Vertex AI Agent Runtime (Reasoning Engines)** with in-place revisions, and serve developers via a modern **Cloud Run** web application with full OpenTelemetry tracing and Cloud Logging.

### System Architecture

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          Client Layer                                  │
│  • Web Browser (via IAP or `gcloud run services proxy`)                │
│  • Google Agents CLI (`agents-cli eval grade / compare`)               │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│  Cloud Run: docshound-frontend       │  │  Cloud Run: docshound-backend │
│  • React + Vite + Nginx              │  │  • FastAPI JSON/SSE Server    │
│  • Port 8080                         │  │  • OpenTelemetry / Tracing    │
└──────────────────────────────────────┘  └──────────────┬───────────────┘
                                                         │
                                                         ▼
                                          ┌──────────────────────────────┐
                                          │   Vertex AI Agent Runtime    │
                                          │  • DocsHoundAgentEngine      │
                                          │  • LangGraph StateGraph      │
                                          │  • Gemini 3.7 Flash          │
                                          └──────────────┬───────────────┘
                                                         │
                                                         ▼
                                          ┌──────────────────────────────┐
                                          │   Google Cloud Observability │
                                          │  • Cloud Logging             │
                                          │  • Cloud Trace               │
                                          └──────────────────────────────┘
```

---

## 2. Environment & Prerequisites

### Required Tools
- **macOS** with Homebrew
- **Python 3.14** (`/opt/homebrew/bin/python3.14`)
- **uv** package manager (`brew install uv`)
- **Google Cloud SDK** (`gcloud`, configured for `agent-clinic-e3-dev`)
- **GitHub CLI** (`gh`, authenticated via `gh auth login`)
- **Node.js 26+ / Bun**

### Project Configuration
```bash
GCP_PROJECT="agent-clinic-e3-dev"
GCP_REGION="us-central1"
VERTEX_MODEL="google/gemini-3.7-flash"
FALLBACK_MODEL="google/gemini-3.5-flash"
STAGING_BUCKET="gs://agent-clinic-e3-dev-agent-runtime-staging"
```

---

## 3. Local Workspace Setup

```bash
# 1. Clone repository
cd ~/GitHub
git clone git@github.com:danielazamorah/docshound.git
cd docshound

# 2. Checkout working branch
git checkout feat/gemini-vertex

# 3. Setup Backend
cd backend
uv sync
cp .env.example .env

# Configure .env with your environment
cat << 'EOF' > .env
VERTEX_PROJECT=agent-clinic-e3-dev
VERTEX_LOCATION=global
VERTEX_PRIMARY_MODEL=google/gemini-3.7-flash
VERTEX_FALLBACK_MODEL=google/gemini-3.5-flash
VERTEX_DEPLOY_LOCATION=us-central1
VERTEX_STAGING_BUCKET=gs://agent-clinic-e3-dev-agent-runtime-staging
DOCSHOUND_DATA_DIR=data
DOCSHOUND_DATABASE_URL=sqlite:///data/docshound.db
EOF

# Append active GitHub token
echo "GITHUB_TOKEN=$(gh auth token)" >> .env

# 4. Setup Frontend
cd ../frontend
npm install
```

---

## 4. Local Rehearsal & Verification

### Run Automated Unit Tests
```bash
cd ~/GitHub/docshound/backend
uv run pytest -v
# Output: 65 passed in 0.52s
```

### Run End-to-End Rehearsal Pipeline
The rehearsal exercises GitHub data retrieval, Gemini 3.7 Flash analysis, documentation discovery, Markdown drafting, and patch generation against `google/adk-python`:

```bash
cd ~/GitHub/docshound
./demo/rehearse.sh adk-dani
```

Expected verification stages:
1. `[PASS] research`: Successfully parsed pinned issues and PRs from GitHub.
2. `[PASS] analyze`: Gemini 3.7 Flash identified documentation gaps and changes.
3. `[PASS] docs`: Inspected docs directory (`docs/guides/README.md`).
4. `[PASS] drafting`: Synthesized ready-to-publish Markdown documentation drafts.
5. `[PASS] preview`: Created unified diff patches without syntax errors.

---

## 5. Vertex AI Agent Runtime: Deployments & In-Place Revisions

Vertex AI Agent Runtime manages LangGraph execution as a serverless **Reasoning Engine**.

### Deploy or Mint a New Revision
```bash
cd ~/GitHub/docshound/backend

# Automatically updates the existing engine (minting a new revision) or creates a new one
PYTHONPATH=. uv run python deploy_agent_runtime.py deploy --display-name docshound-langgraph-agent
```

### List Deployed Engines & Revisions
```bash
PYTHONPATH=. uv run python deploy_agent_runtime.py list
```

### Query Deployed Agent Directly
```bash
PYTHONPATH=. uv run python deploy_agent_runtime.py query \
  projects/901293631737/locations/us-central1/reasoningEngines/4889107645522247680 \
  --repo google/adk-python
```

---

## 6. Deploying Full Stack to Cloud Run & Enterprise Access

### 1. Deploy the FastAPI Backend
```bash
cd ~/GitHub/docshound/backend

gcloud run deploy docshound-backend \
  --source . \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --set-env-vars="VERTEX_PROJECT=agent-clinic-e3-dev,VERTEX_LOCATION=global,VERTEX_PRIMARY_MODEL=google/gemini-3.7-flash,VERTEX_FALLBACK_MODEL=google/gemini-3.5-flash" \
  --quiet
```

### 2. Deploy the React Frontend
```bash
cd ~/GitHub/docshound/frontend

BACKEND_URL=$(gcloud run services describe docshound-backend --project=agent-clinic-e3-dev --region=us-central1 --format="value(status.url)")

gcloud run deploy docshound-frontend \
  --source . \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --set-env-vars="VITE_API_BASE_URL=${BACKEND_URL}" \
  --quiet
```

### 3. Accessing Cloud Run with Enterprise Org Policies (`403 Forbidden` Fix)

In environments where organization policies restrict `allUsers`, raw browser URL access will return `403 Forbidden` because web browsers do not send IAM Identity tokens by default.

To interact with the deployed application securely:

```bash
# Terminal 1: Proxy Frontend to http://localhost:8080
gcloud run services proxy docshound-frontend \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --port=8080

# Terminal 2: Proxy Backend to http://localhost:8000
gcloud run services proxy docshound-backend \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --port=8000
```

Open `http://localhost:8080` in Chrome to interact with the live Cloud Run application with full authentication.

---

## 7. Observability, Telemetry & Cloud Logging Queries for Evals

### Telemetry Architecture

- **Local Execution**: Traces emit through OpenInference/OTel, viewable via local SQLite database, in-process SSE stream (`/api/v1/runs/{id}/events`), or LangSmith (`LANGSMITH_API_KEY`).
- **Cloud Run & Agent Runtime**: Execution logs and OpenTelemetry spans stream directly to **Google Cloud Logging** (`aiplatform.googleapis.com/ReasoningEngine` and `cloud_run_revision`) and **Google Cloud Trace**.

### Useful `gcloud logging read` Commands for Evaluation

```bash
# 1. Read Vertex AI Reasoning Engine execution and OTel lifecycle logs
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine"' \
  --project=agent-clinic-e3-dev \
  --limit=25 \
  --format="table(timestamp,textPayload)"

# 2. Read Cloud Run Backend API requests and trace events
gcloud logging read 'resource.type="cloud_run_revision" resource.labels.service_name="docshound-backend"' \
  --project=agent-clinic-e3-dev \
  --limit=25 \
  --format="table(timestamp,httpRequest.requestMethod,httpRequest.requestUrl,httpRequest.status,textPayload)"

# 3. Export structured logs as JSON for evaluation datasets
gcloud logging read 'resource.type="cloud_run_revision" resource.labels.service_name="docshound-backend"' \
  --project=agent-clinic-e3-dev \
  --limit=100 \
  --format="json" > /tmp/docshound_eval_traces.json
```

---

## 8. Evaluating with Agents CLI (`agents-cli`)

```bash
# Grade agent documentation outputs against ground truth rubrics
agents eval grade \
  --agent-endpoint="http://localhost:8000/api/v1/runs" \
  --eval-dataset="./tests/eval_dataset.json" \
  --metric="faithfulness,completeness,actionability"

# Compare Gemini 3.7 Flash candidate against Gemini 3.5 Flash baseline
agents eval compare \
  --candidate-model="google/gemini-3.7-flash" \
  --baseline-model="google/gemini-3.5-flash" \
  --dataset="./tests/eval_dataset.json"
```

---

## 9. Live Recording Script (Episode 3)

### Act 1: The Problem (0:00 - 1:30)
- **Visual**: Dani on camera + split screen with open source repo (`google/adk-python`).
- **Talking Point**: "Code moves fast, docs lag behind. When PRs merge without docs updates, users get stuck. Today in Episode 3, we build DocsHound—an autonomous documentation intelligence agent powered by LangGraph, Vertex AI Agent Runtime, and Gemini 3.7 Flash."

### Act 2: Local Agent Workflow & Architecture (1:30 - 4:00)
- **Visual**: Terminal & IDE (`app/langgraph_agent.py` and `demo/rehearse.sh`).
- **Talking Point**:
  - Walk through the LangGraph StateGraph nodes (`research` -> `analyze` -> `search_docs` -> `draft` -> `store`).
  - Run `./demo/rehearse.sh adk-dani`.
  - Show how Gemini 3.7 Flash discovers new features in PR diffs and cross-references existing Markdown guides.

### Act 3: Deployment & In-Place Revisions on Vertex AI Agent Runtime (4:00 - 6:30)
- **Visual**: Running `python deploy_agent_runtime.py deploy` and checking Google Cloud Console Reasoning Engines.
- **Talking Point**:
  - "With Vertex AI Agent Runtime, deploying and minting new revisions for our LangGraph agent is one command—no custom Kubernetes or infrastructure boilerplate needed."
  - Show querying the reasoning engine via CLI: `python deploy_agent_runtime.py query ... --repo google/adk-python`.

### Act 4: The Web Experience on Cloud Run (6:30 - 8:30)
- **Visual**: Browser at `http://localhost:8080` (via `gcloud run services proxy` or Cloud Run URL).
- **Talking Point**:
  - Trigger a new analysis run for a repo.
  - Watch real-time Server-Sent Events (SSE) streaming agent reasoning steps.
  - Review the generated documentation diff patch.
  - Approve finding and trigger PR creation.

### Act 5: Observability, Evals with Agents CLI & Outro (8:30 - 10:00)
- **Visual**: Google Cloud Logging / Trace dashboard and `agents-cli eval grade` output.
- **Talking Point**:
  - Show live telemetry pouring into Cloud Logging.
  - Run `agents-cli eval grade` to quantitatively evaluate documentation completeness and faithfulness.
  - Summary and call-to-action for developers to try Agent Runtime.
