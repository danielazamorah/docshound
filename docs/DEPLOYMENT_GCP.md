# Deploying DocsHound to Google Cloud Platform

This guide documents how to deploy DocsHound to **Google Cloud Platform (GCP)** using **Vertex AI Agent Runtime (Reasoning Engines)** and **Cloud Run**, with native support for **Gemini 3.7 Flash**.

---

## Overview

DocsHound on GCP provides:
- **Managed Agent Execution**: Deploy the core LangGraph workflow to **Vertex AI Agent Runtime** as a scalable, serverless Reasoning Engine.
- **Serverless Web Application**: Host the FastAPI backend and React frontend on **Cloud Run** with independent autoscaling and custom domain/IAM bindings.
- **Gemini 3.7 Flash Integration**: Use Vertex AI's OpenAI-compatible endpoints or native SDK integrations with automatic fallback to Gemini 3.5 Flash.
- **Observability**: Vendor-neutral OpenTelemetry / OpenInference tracing exportable to Google Cloud Trace or LangSmith.

---

## Prerequisites

1. **Google Cloud Project**:
   - A GCP project with billing enabled (e.g., `PROJECT_ID=agent-clinic-e3-dev`).
   - Enabled APIs:
     ```bash
     gcloud services enable \
       aiplatform.googleapis.com \
       run.googleapis.com \
       cloudbuild.googleapis.com \
       artifactregistry.googleapis.com \
       storage.googleapis.com
     ```

2. **Google Cloud Storage Bucket** for Agent Runtime staging:
     ```bash
     gsutil mb -p ${PROJECT_ID} -l us-central1 gs://${PROJECT_ID}-agent-runtime-staging
     ```

3. **Required IAM Permissions**:
   - Ensure the Compute Service Account (`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`) and Cloud Build Service Account have the following roles:
     - `roles/storage.admin`
     - `roles/artifactregistry.admin`
     - `roles/aiplatform.user`
     - `roles/run.admin`

4. **Tools Installed Locally**:
   - Google Cloud SDK (`gcloud`)
   - Python 3.14 with `uv`
   - Node.js / Bun

---

## 1. Deploying the LangGraph Agent to Vertex AI Agent Runtime

Vertex AI Agent Runtime allows you to deploy DocsHound's LangGraph workflow directly as a managed **Reasoning Engine**.

### Configuration

Set the required environment variables in `backend/.env` or export them in your shell:

```bash
export VERTEX_PROJECT="your-project-id"
export VERTEX_LOCATION="global"
export VERTEX_DEPLOY_LOCATION="us-central1"
export VERTEX_STAGING_BUCKET="gs://your-project-id-agent-runtime-staging"
export VERTEX_PRIMARY_MODEL="google/gemini-3.7-flash"
export VERTEX_FALLBACK_MODEL="google/gemini-3.5-flash"
```

### Deploying the Reasoning Engine

Run the deployment script from the `backend/` directory:

```bash
cd backend
PYTHONPATH=. uv run python deploy_agent_runtime.py deploy --display-name docshound-langgraph-agent
```

This packages the backend dependencies, uploads them to your staging bucket, and creates a Vertex AI Reasoning Engine instance. The command outputs the deployed resource name (e.g., `projects/<PROJECT_NUMBER>/locations/us-central1/reasoningEngines/<REASONING_ENGINE_ID>`).

### Listing Deployed Agents

```bash
PYTHONPATH=. uv run python deploy_agent_runtime.py list
```

### Querying the Deployed Agent

You can query the remote reasoning engine directly via CLI:

```bash
PYTHONPATH=. uv run python deploy_agent_runtime.py query \
  projects/<PROJECT_NUMBER>/locations/us-central1/reasoningEngines/<REASONING_ENGINE_ID> \
  --repo google/adk-python
```

---

## 2. Deploying to Cloud Run

The frontend and backend can be deployed independently to Cloud Run.

### Step 1: Deploy the FastAPI Backend

```bash
cd backend

gcloud run deploy docshound-backend \
  --source . \
  --project=${PROJECT_ID} \
  --region=us-central1 \
  --set-env-vars="VERTEX_PROJECT=${PROJECT_ID},VERTEX_LOCATION=global,VERTEX_PRIMARY_MODEL=google/gemini-3.7-flash,VERTEX_FALLBACK_MODEL=google/gemini-3.5-flash" \
  --quiet
```

Retrieve the backend URL:
```bash
BACKEND_URL=$(gcloud run services describe docshound-backend --project=${PROJECT_ID} --region=us-central1 --format="value(status.url)")
echo "Backend URL: ${BACKEND_URL}"
```

### Step 2: Configure Invoker Access

If deploying for internal organization use:
```bash
gcloud run services add-iam-policy-binding docshound-backend \
  --region=us-central1 \
  --member="domain:yourdomain.com" \
  --role=roles/run.invoker \
  --project=${PROJECT_ID}
```

Or for public access (if permitted by organization policy):
```bash
gcloud run services add-iam-policy-binding docshound-backend \
  --region=us-central1 \
  --member="allUsers" \
  --role=roles/run.invoker \
  --project=${PROJECT_ID}
```

### Step 3: Deploy the React Frontend

Deploy the frontend container, pointing `VITE_API_BASE_URL` to the backend Cloud Run service:

```bash
cd ../frontend

gcloud run deploy docshound-frontend \
  --source . \
  --project=${PROJECT_ID} \
  --region=us-central1 \
  --set-env-vars="VITE_API_BASE_URL=${BACKEND_URL}" \
  --quiet
```

Allow invoker access to the frontend:
```bash
gcloud run services add-iam-policy-binding docshound-frontend \
  --region=us-central1 \
  --member="domain:yourdomain.com" \
  --role=roles/run.invoker \
  --project=${PROJECT_ID}
```

---

## 3. Evaluation with Google Agents CLI (`agents-cli`)

DocsHound evaluation can be performed using Google's open-source `agents-cli`:

### Evaluation Rubric & Grading

```bash
# Install Agents CLI if needed
pip install agents-cli

# Run automated grading of agent documentation synthesis
agents eval grade \
  --agent-endpoint="${BACKEND_URL}/api/v1/runs" \
  --eval-dataset="./tests/eval_dataset.json" \
  --metric="faithfulness,completeness,actionability"
```

### Comparative Model Benchmarks

Compare quality between primary model (`gemini-3.7-flash`) and baseline fallback:

```bash
agents eval compare \
  --candidate-model="google/gemini-3.7-flash" \
  --baseline-model="google/gemini-3.5-flash" \
  --dataset="./tests/eval_dataset.json"
```

---

## 4. Observability and Tracing

DocsHound instruments all LangGraph node transitions and Gemini model invocations using OpenTelemetry. Traces can be exported to Google Cloud Trace or any OTLP-compliant collector.

To configure OTLP export:
```bash
export OTEL_SERVICE_NAME="docshound"
export OTEL_EXPORTER_OTLP_ENDPOINT="https://your-collector-endpoint"
```
