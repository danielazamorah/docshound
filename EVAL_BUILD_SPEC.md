# For Antigravity — Build the REAL Agents CLI Eval Flow (Ep3)

Hi A. 👋 One focused job here. Read the whole file once, then do it **one step at a time** — don't batch, don't one-shot. Each step has a check; don't move on until it passes.

## The one goal
Replace the hand-rolled scoring in `backend/run_evals.py` with a **real Google Agents CLI** evaluation flow — so on camera we run the actual `agents-cli eval grade` / `agents-cli eval compare`, not a self-graded print-out. The episode literally teaches the Agents CLI, so the code has to use it.

## Why we're redoing this (read once, don't skip)
The current `backend/run_evals.py` judges Gemini-3.7 **with Gemini-3.7** and prints `5/5` on every metric even when the judge call returns nothing (`judge_result.get('issue_validity', 5)`). A perfect board is not believable and it never touches `agents-cli`. We're keeping the *good* parts of that file (scenario loading, the metadata math) and moving the *grading* to the real CLI with an **independent judge model**.

## Guardrails (these matter)
1. **Validate every command and schema against your installed CLI before using it.** Run `agents-cli --help`, `agents-cli eval --help`, `agents-cli eval grade --help`, `agents-cli eval compare --help`, `agents-cli eval metric list`. Flags and the dataset schema shift between releases — trust the `--help` output over anything in this doc.
2. **Independent judge.** The judge model must NOT be the model under test. Under test = `google/gemini-3.7-flash`. Use a different judge (e.g. a Gemini Pro or 3.5 model you have access to) via the metric's `judge_model` field.
3. **Additive, don't delete.** Keep `run_evals.py` working as a fallback; put the new flow in its own files. Don't touch `demo/scenarios/opencode.json`.
4. **Step by step is the point.** This flow is what we perform on camera as separate beats — don't collapse it into one script that does everything silently.
5. **No secrets in git.** GitHub token via env/Secret Manager only.

## Build it in order

### Step 1 — Confirm the CLI and the dataset schema
- Run the `--help` commands above. Write down (in a scratch note) the exact: grade command + flags, compare command + flags, and where the config path is expected.
- Find the **eval-dataset JSON schema** the CLI expects. Look for a sample (docs, `agents-cli eval generate` output shape, or the "Migrating Eval Datasets" docs page). We need the real field names — likely `eval_cases[].agent_data.turns` with per-turn `prompt` / `response` / tool calls, but **confirm, don't assume.**
- ✅ Check: you can state the exact grade/compare commands and paste one real example of the dataset JSON shape.

### Step 2 — Capture a real trace (Interact)
- Run the **live backend** (not `demo/rehearse.py` — it emits no spans) against `adk-dani` with tracing export ON. `setup_tracing()` only exports if `LANGSMITH_API_KEY` or an explicit `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is set — set one, or you get nothing.
- Save the run's OpenInference spans to a file (the trace tree: `docshound.agent` root, `tool.<name>` spans, LLM spans).
- ✅ Check: you have a real trace file with the agent's steps for the adk-dani run.

### Step 3 — Write the trace → EvaluationDataset converter
- New file: `backend/eval/convert_traces.py`. Read the OpenInference spans from Step 2 and emit ONE eval-dataset JSON in the exact schema from Step 1 (map: user input → `prompt`; final findings/draft → `response`; the node/tool steps → the per-turn/steps field; keep the tool names + inputs/outputs).
- Also carry the raw operational signals through (latency, tokens, tool-call count, model served, pages inspected) so the computed metric can read them — reuse the math already in `run_evals.py`.
- ✅ Check: `convert_traces.py` produces a dataset file that validates against the schema (grade accepts it without a parse error).

### Step 4 — Write `eval_config.yaml` (three metric kinds, independent judge)
- New file: `backend/tests/eval/eval_config.yaml` (or wherever `--help` says the config lives). Include all three kinds so the episode can show them:
  - **Managed metric** — pick one that fits a single-turn doc task from `agents-cli eval metric list` (e.g. a groundedness / final-response-quality style metric). Use the exact name the CLI lists.
  - **Custom rubric (LLM-as-judge)** — `issue_relevancy`: judges whether the issue DocsHound picked is genuinely relevant, actionable, and correctly documented. `prompt_template` scores `{prompt}` / `{response}` / `{agent_data}`, returns JSON `{"score": 1-5, "explanation": "..."}`. Set `judge_model` to the **independent** model and `judge_model_sampling_count: 3`.
  - **Computed (CodeExecutionMetric, `execution: local`)** — `source_coverage` (or turn/latency metric): a plain Python `custom_function` reading the metadata you carried in Step 3. No LLM.
- ✅ Check: `agents-cli eval metric list` shows your managed metric name is real; the YAML parses.

### Step 5 — Grade (Evaluate)
- Run the real command from Step 1, e.g. `agents-cli eval grade --traces <dir> --config backend/tests/eval/eval_config.yaml` (use the actual flags).
- Save the results JSON as the **baseline** (e.g. `eval/results/baseline.json`).
- ✅ Check: you get real, varied scores (NOT a clean 5/5 row). If everything is 5/5, the judge is failing silently — fix it, don't ship it.

### Step 6 — Iterate + Compare (Improve)
- Apply the hypothesis change (scope research to the target area of the repo instead of scanning everything), re-capture a trace (Steps 2–3), grade again → `candidate.json`.
- Run `agents-cli eval compare baseline.json candidate.json` (real flags).
- ✅ Check: `issue_relevancy` moves up between baseline and candidate; the compare output shows the delta.

### Step 7 — Display
- Render the results as the on-camera scoreboard. Target look = the agent-eval report (Overview KPIs + radar of judge scores + a metrics table; Per-Question; Iteration History). **Do not build/show an "AI Analysis" tab** — that analysis is your job live, not a tab.
- ✅ Check: opening the report shows both metric families and the baseline→candidate trend.

## Acceptance (all must be true before recording)
- [ ] `agents-cli eval grade` runs against DocsHound's real trace and returns non-trivial scores.
- [ ] `agents-cli eval compare` shows `issue_relevancy` improving after the scoping change.
- [ ] Judge model ≠ model under test.
- [ ] Three metric kinds present in `eval_config.yaml` (managed + rubric + computed).
- [ ] `opencode.json` untouched; `run_evals.py` still works as fallback.
- [ ] Every flag/command used matches your installed `agents-cli --help`.

## Maps to the on-camera beats (keep runbook + script in sync)
Step 2 = Interact · Steps 3–4 = crawl code → propose + validate metrics/data with Matt · Step 5 = grade · Step 7 = scoreboard · Step 6 = iterate + compare. That maps to Scenes 3–5 of the episode. See `EPISODE_RUNBOOK.md` Part B for the on-camera step order. If any command/name changes here, update the runbook so both agree.

## Leave findings here
When done (or blocked), drop a short note (or a PR comment) with: the exact commands that worked, the real metric names you used, and the actual baseline vs candidate scores — so we can replace the placeholder scores in the script.
