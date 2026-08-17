# Deploying DocsHound to Google Cloud Platform

This guide documents how to deploy, manage, observe, and evaluate DocsHound on **Google Cloud Platform (GCP)** using **Vertex AI Agent Runtime (Reasoning Engines)** and **Cloud Run**, with native support for **Gemini 3.7 Flash**.

---

## Architecture Overview

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          Client Layer                                  │
│  • Web Browser (via IAP or `gcloud run services proxy`)                │
│  • Google Agents CLI (`agents-cli eval grade / compare`)               │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │                                 │
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│       Cloud Run: Frontend            │  │     Cloud Run: Backend        │
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

## 1. Vertex AI Agent Runtime: Deployment & Revisions

Vertex AI Agent Runtime executes DocsHound's LangGraph workflow as a managed, serverless **Reasoning Engine**.

### Configuration

Set the environment variables in `backend/.env` or export them in your shell:

```bash
export VERTEX_PROJECT="agent-clinic-e3-dev"
export VERTEX_LOCATION="global"
export VERTEX_DEPLOY_LOCATION="us-central1"
export VERTEX_STAGING_BUCKET="gs://agent-clinic-e3-dev-agent-runtime-staging"
export VERTEX_PRIMARY_MODEL="google/gemini-3.7-flash"
export VERTEX_FALLBACK_MODEL="google/gemini-3.5-flash"
```

### Deploying & Minting Revisions

Instead of creating duplicate reasoning engines for every change, DocsHound supports **in-place revision minting**:

```bash
cd backend

# Deploy or automatically update the existing engine (mints a new revision)
PYTHONPATH=. uv run python deploy_agent_runtime.py deploy --display-name docshound-langgraph-agent

# Explicitly update an existing Reasoning Engine revision
PYTHONPATH=. uv run python deploy_agent_runtime.py update \
  projects/901293631737/locations/us-central1/reasoningEngines/<REASONING_ENGINE_ID>
```

### Managing Revisions & Traffic Splitting

In Agent Runtime, each code or configuration update mints an immutable revision (`runtimeRevisions/{revision_id}`).

- **Default Mode**: `trafficSplitAlwaysLatest {}` (routes 100% of traffic to the latest active revision).
- **Manual Traffic Split**:
  ```json
  {
    "trafficConfig": {
      "trafficSplitManual": {
        "targets": [
          {"runtimeRevisionName": "projects/.../reasoningEngines/.../runtimeRevisions/rev-1", "percent": 90},
          {"runtimeRevisionName": "projects/.../reasoningEngines/.../runtimeRevisions/rev-2", "percent": 10}
        ]
      }
    }
  }
  ```

### Listing, Querying, & Deleting Engines

```bash
# List deployed engines
PYTHONPATH=. uv run python deploy_agent_runtime.py list

# Query the deployed engine
PYTHONPATH=. uv run python deploy_agent_runtime.py query \
  projects/901293631737/locations/us-central1/reasoningEngines/<REASONING_ENGINE_ID> \
  --repo google/adk-python

# Clean up / delete an obsolete engine
PYTHONPATH=. uv run python deploy_agent_runtime.py delete \
  projects/901293631737/locations/us-central1/reasoningEngines/<OBSOLETE_ENGINE_ID>
```

---

## 2. Cloud Run Deployment & Enterprise Security Access

### Step 1: Deploy Backend to Cloud Run

```bash
cd backend

gcloud run deploy docshound-backend \
  --source . \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --set-env-vars="VERTEX_PROJECT=agent-clinic-e3-dev,VERTEX_LOCATION=global,VERTEX_PRIMARY_MODEL=google/gemini-3.7-flash,VERTEX_FALLBACK_MODEL=google/gemini-3.5-flash" \
  --quiet
```

### Step 2: Deploy Frontend to Cloud Run

```bash
cd ../frontend

BACKEND_URL=$(gcloud run services describe docshound-backend --project=agent-clinic-e3-dev --region=us-central1 --format="value(status.url)")

gcloud run deploy docshound-frontend \
  --source . \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --set-env-vars="VITE_API_BASE_URL=${BACKEND_URL}" \
  --quiet
```

### Resolving `403 Forbidden` in Enterprise Environments

In enterprise or Google corporate environments, GCP Organization Policies (such as `constraints/iam.allowedPolicyMemberDomains`) disallow public unauthenticated access (`allUsers`). When you visit a raw `*.run.app` URL in a browser, the browser does not attach Google IAM identity tokens, resulting in:
`Error: Forbidden - Your client does not have permission to get URL / from this server.`

#### Option A: Local Authenticated Developer Proxy (Recommended for Dev & Demos)
Use `gcloud run services proxy` to run a local proxy that automatically signs all requests with your active `gcloud` identity:

```bash
# Proxy the Frontend to http://localhost:8080
gcloud run services proxy docshound-frontend \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --port=8080

# Proxy the Backend to http://localhost:8000
gcloud run services proxy docshound-backend \
  --project=agent-clinic-e3-dev \
  --region=us-central1 \
  --port=8000
```

Now you can open `http://localhost:8080` directly in any browser with full authenticated access.

#### Option B: Corporate Identity-Aware Proxy (IAP) / Load Balancer (For Production)
For production browser access across your team:
1. Set up an external/internal Application Load Balancer with Cloud Run as a Serverless Network Endpoint Group (NEG).
2. Enable **Identity-Aware Proxy (IAP)** on the backend service.
3. Configure OAuth consent screen to grant browser SSO access to your domain/group members.

---

## 3. Telemetry, Tracing & Cloud Logging

DocsHound implements vendor-neutral OpenTelemetry instrumentation enriched with **OpenInference** semantic conventions (`AGENT` root spans, `TOOL` execution spans).

### How DocsHound Telemetry Works (`backend/app/tracing.py`)

- **Root Agent Span**: Wrapped around `run_agent()`, recording metadata (repository, documentation source, issue counts) without exposing confidential token payloads.
- **Tool Spans**: Context managers instrument GitHub API interactions, documentation parsing, Markdown drafting, and diff generation.
- **Model Auto-Instrumentation**: Automatically instruments LangGraph nodes and OpenAI/Gemini SDK calls.

### Telemetry Destination: Local vs. Cloud

| Environment | Telemetry Sink | Storage & Format | How to Extract for Evals |
| :--- | :--- | :--- | :--- |
| **Local Run** (`./run.sh` / `./demo/rehearse.sh`) | In-memory event bus (`app/events.py`) & LangSmith / local OTLP collector | SQLite (`docshound.db`), in-memory SSE stream, or OTLP trace JSON | • Query `/api/v1/runs/{id}/events`<br>• LangSmith trace export<br>• Local OTLP trace file |
| **Cloud Run** (`docshound-backend`) | **Google Cloud Logging** (`run.googleapis.com/stdout`) | Cloud Logging JSON payload & HTTP request logs | `gcloud logging read 'resource.type="cloud_run_revision"'` |
| **Agent Runtime** (`ReasoningEngine`) | **Google Cloud Logging** (`aiplatform.googleapis.com/ReasoningEngine`) & Cloud Trace | Cloud Logging records with OTEL lifecycle logs | `gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine"'` |

### Cloud Logging Query Commands for Evaluation

Extract execution traces and metrics directly using `gcloud logging read`:

```bash
# 1. Query Agent Runtime Reasoning Engine logs
gcloud logging read 'resource.type="aiplatform.googleapis.com/ReasoningEngine"' \
  --project=agent-clinic-e3-dev \
  --limit=30 \
  --format="table(timestamp,textPayload)"

# 2. Query Cloud Run Backend API requests and trace events
gcloud logging read 'resource.type="cloud_run_revision" resource.labels.service_name="docshound-backend"' \
  --project=agent-clinic-e3-dev \
  --limit=30 \
  --format="table(timestamp,httpRequest.requestMethod,httpRequest.requestUrl,httpRequest.status,textPayload)"

# 3. Export structured logs as JSON for automated evaluation pipelines
gcloud logging read 'resource.type="cloud_run_revision" resource.labels.service_name="docshound-backend"' \
  --project=agent-clinic-e3-dev \
  --limit=100 \
  --format="json" > /tmp/docshound_cloud_traces.json
```

---

## 4. Evaluation with Google Agents CLI (`agents-cli`)

Use Google Agents CLI to evaluate DocsHound's documentation synthesis quality:

```bash
# Grade documentation accuracy and gap completeness against evaluation dataset
agents eval grade \
  --agent-endpoint="http://localhost:8000/api/v1/runs" \
  --eval-dataset="./tests/eval_dataset.json" \
  --metric="faithfulness,completeness,actionability"

# Compare Gemini 3.7 Flash vs Gemini 3.5 Flash baseline
agents eval compare \
  --candidate-model="google/gemini-3.7-flash" \
  --baseline-model="google/gemini-3.5-flash" \
  --dataset="./tests/eval_dataset.json"
```
