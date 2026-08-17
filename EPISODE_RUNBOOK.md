# Ep3 Runbook — Simple & Step-by-Step

Recording runbook for Agent Clinic Ep3 (DocsHound + Google Agents CLI + Antigravity, on Vertex AI Agent Runtime). Branch: `rollback`.

## The one rule (for Antigravity)

**Do ONE step. Then STOP and wait for the go-ahead. Never run ahead, never batch steps, never "run the whole thing."** The whole episode is showing the audience the steps, one at a time, so Matt and I can react between them. Every step below ends with a ✋ gate. When you hit ✋, stop and wait.

If a step fails, stop and say what broke — don't improvise a fix on camera.

---

## Part A — Before we hit record (prep, off camera)

Get all of these green first. If one is red, fix it before recording, not during.

1. **Branch.** We record from `rollback`. `git checkout rollback`.
2. **Backend env + deps.** `.env` has `VERTEX_PROJECT=agent-clinic-e3-dev`, `VERTEX_LOCATION=global`, `VERTEX_PRIMARY_MODEL=google/gemini-3.7-flash`, `VERTEX_FALLBACK_MODEL=google/gemini-3.5-flash`, and a fresh `GITHUB_TOKEN`. Then `uv sync`.
3. **Tests green.** `uv run pytest` — all pass.
4. **Telemetry export is ON.** Set `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` (or `LANGSMITH_API_KEY`) *before* any run — otherwise DocsHound emits **no** spans and we have nothing to evaluate. (Do not rely on `gcloud logging read` as "eval data" — Cloud Run request logs are not OpenInference traces.)
5. **Agent Runtime engine answers.** Confirm the live engine responds (use the current engine ID — confirm which one is live before filming; the ID in old notes may be stale):
   `PYTHONPATH=. uv run python deploy_agent_runtime.py query <reasoningEngines/ID> --repo google/adk-python`
6. **Cloud Run up.** Frontend + backend reachable via `gcloud run services proxy` (frontend :8080, backend :8000).
7. **Agents CLI installed.** `agents-cli --help` works. Confirm the real binary name and the real flags for `eval grade` / `eval compare` / `eval metric list` — do not trust remembered flags.
8. **The real eval flow is built.** Follow `EVAL_BUILD_SPEC.md`: `eval_config.yaml` (independent judge + a computed metric), the trace→dataset converter, and real `agents-cli eval grade`/`compare`. ⚠️ This is the one blocker that makes Scene 4 demonstrable — build it before recording.

✋ All eight green → we can record.

---

## Part B — On camera, one step at a time

Each step: do the action, narrate it, then ✋ stop and wait. Matt reacts, I react, then "go" for the next one.

### Run the agent (Scene 2)
1. Run DocsHound against `google/adk-python` via the rehearsal harness: `./demo/rehearse.sh adk-dani`. Let it go research → analyze → search docs → draft (stops before the PR). ✋
2. Pull the trace from that run (the OpenInference spans, from the live run with export ON). ✋

### Build the eval, step by step (Scene 4)
3. Send a subagent to crawl DocsHound's code **and** the trace from step 2, with one goal: what's worth measuring, and what good eval data looks like. Present findings. ✋ (Matt validates.)
4. Propose a handful of scenarios + the eval data they'd produce. Show them; don't accept blind. ✋ (Review together.)
5. Run the agent across the agreed scenarios; capture the traces. ✋
6. Convert the traces → the Agents-CLI eval dataset, and pull the operational metadata (latency, tokens, tool calls, model served, pages read) from the same traces. Show both. ✋
7. Build the metrics in `eval_config.yaml` together — the LLM-judge rubric (independent judge model) + the computed metric. Read each definition; accept one at a time. ✋
8. Grade: `agents-cli eval grade` (real flags per Part A.7). Show the run. ✋
9. Open the HTML report (Overview: KPIs + judge radar + computed table). Do **not** open any "AI Analysis" tab — we do the analysis live. ✋ (React.)

### Iterate (Scene 5)
10. Form the hypothesis with Matt (e.g. scope research to the target area, not the whole repo). ✋
11. Let Antigravity draft the change; read the plan; apply it. ✋
12. Re-run the **exact same** scenarios and `agents-cli eval compare` baseline vs candidate. Show the metric move + the iteration-history trend. ✋
13. (Optional) Push the change as a new Agent Runtime revision and grade the deployed one with the same scenarios — "local while you iterate, deployed before you ship." ✋

---

## What changed from the earlier runbook, and why

- **Removed the fake Agents CLI commands** (`agents eval grade --agent-endpoint … --metric "faithfulness,completeness,actionability"`, `agents eval compare --candidate-model …`). Those flags and metric names aren't real — they'd fail on camera. Replaced with the real flow (Part A.7–8 + `EVAL_BUILD_SPEC.md`).
- **Removed "stream logs to Cloud Logging = eval data."** Misleading — `setup_tracing()` only exports if the env is set, and request logs ≠ OpenInference traces. Replaced with "turn export ON, capture real traces" (A.4).
- **Trimmed the big ASCII architecture, deep IAM/403 walkthroughs, and version specifics.** True but heavy and easy to trip on. Kept only what you actually run.
