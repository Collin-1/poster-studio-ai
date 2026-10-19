# Poster Studio AI

A functional local poster workspace with React, FastAPI, SQLite, four role-specific agents, explicit human approvals, editable SVG export, and a standalone agent playground. Mock mode runs entirely without an API key.

## Run locally

Requirements: standard CPython 3.11+ (not MSYS Python), Node.js 20.19+ or 22+, npm.

From the repository root, on Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
.\.venv\Scripts\python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. Build the frontend before starting the backend: FastAPI serves `frontend/dist` when present at startup. On macOS/Linux use `.venv/bin/python` and `npm` instead of the Windows paths/`npm.cmd`.

For frontend development, run the backend as above and, in another terminal, `cd frontend` then `npm.cmd run dev`. Open **http://127.0.0.1:5173**; Vite proxies `/api` to FastAPI. Backend interactive API docs: **http://127.0.0.1:8000/docs**.

If using the project-local embedded Python runtime prepared during development, use `.\.runtime\python.exe` in place of `.\.venv\Scripts\python`. It is ignored by Git and is not required on other machines.

## Make your first poster

1. Choose **mock**, name a project, and click **New poster**.
2. Tell the Creative Director your goal, audience, style, and required facts. Reply to its questions as often as needed, then edit and approve the structured brief.
3. Review the Copywriter's headline, supporting content and CTA. Edit directly or send feedback, then approve the copy.
4. Click **Generate poster**. The Visual Designer chooses a palette/motif; the renderer creates SVG text and vector shapes. The Quality Critic checks alignment and measured contrast. A failing critique triggers at most one automatic design revision, then a second check.
5. Inspect the poster and execution log. Edit colors/motif and check again, or download the SVG and edit its text and shapes in a vector editor.

Facts remain your responsibility. Missing event details should be supplied before approval. The critic sees structured layout data and contrast metrics, not a rasterized image. It cannot verify arbitrary visual appearance or real-world event accuracy.

## Architecture and state handoffs

`backend/models.py` defines the typed contracts. `providers.py` owns mock/replay/OpenAI adapters and response validation. `main.py` orchestrates approval gates, transactions, logs and persistence. `svg.py` renders escaped, editable text into a constrained SVG template; providers never emit executable SVG or HTML. `frontend/src/main.jsx` contains the workspace and playground.

```text
collecting → brief_review → [human approves brief]
  → copy_review → [human approves copy]
  → ready_to_design → [human starts generation]
  → designer → critic → (optional designer revision → critic)
  → complete OR needs_attention
```

Only the Creative Director can run before brief approval, and only approved copy reaches the designer. Copy/layout changes in the playground never modify project state. Layout edits after generation preserve approved text and rerun the critic without automatic revisions. Start a fresh project to change an already approved brief or copy.

SQLite stores full project documents, approved artifacts, conversation, design history and timestamped agent inputs/results (results are logged; request context is reflected by approved artifacts). Each action is atomic under a SQLite write transaction. Version checks reject stale tabs and duplicate actions with HTTP 409. Failed provider calls preserve the previous workflow state and add an error log. Logs appear after each request completes; they are not a token stream. This intentionally simple local implementation serializes writes, including provider calls. It is not a multi-user job queue.

The four agents are separate role contracts and prompts coordinated sequentially; they are not four background OS processes. SQLite survives restarts at `data/poster-studio.db`. Secrets stay in the backend environment. This app has no authentication and is intended to bind to loopback only.

## Providers

Copy `.env.example` to `.env`. Provider selection is saved on each project; choose the provider in the new-project form or playground. `AI_PROVIDER` supplies the API's default if a provider is omitted.

- **mock**: deterministic, offline development responses. Demonstrates orchestration, not language-model intelligence; edit the draft fields to supply precise content.
- **replay**: validates saved outputs. The bundled `backend/fixtures/demo.json` uses explicit `"key":"*"` entries, so it always replays the same demo poster irrespective of input. Exact recordings use a SHA-256 of agent + canonical request context. Missing matches fail clearly; they do not silently call another provider.
- **openai**: set `OPENAI_API_KEY` and `OPENAI_MODEL` (example: `gpt-4.1-mini`, subject to your account's access). Calls the official Responses API with JSON Schema structured outputs and `store=False`. API use is separately billed. No credentials are sent to React. Network/provider errors leave workflow state unchanged.

To record validated calls, set `RECORD_PATH=data/session.jsonl`, use mock or OpenAI, and run a workflow/playground experiment. Then clear `RECORD_PATH`, set `REPLAY_PATH=data/session.jsonl`, restart the backend, and repeat the same inputs with replay. Exact requests must match, including feedback and conversation history; project IDs and timestamps are not in provider context. Recordings contain user content, so keep them private. Record/replay can be used for every agent independently.

### Sign in with ChatGPT investigation — 19 October 2026

Official documentation now describes optional ChatGPT plan usage for **open-source and locally hosted apps**, with user consent for eligible Responses API requests. This makes it a plausible future provider for this local application, subject to the actual user's plan/workspace eligibility. It is not equivalent to a regular API key or general access to ChatGPT conversations. See the [official overview](https://developers.openai.com/siwc/token-sharing-open-source).

The documented integration needs a stable host identifier and supported OAuth registration/sign-in, secure token handling and usage controls. Paid/remotely hosted applications have a separate interest route; the [commercial client-ID page](https://developers.openai.com/siwc/request-client-id) describes select partners and a waitlist. This repository has no declared open-source license yet, so publishing it as OSS would also require an explicit licensing decision.

The [preview limitations](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations) require streaming, `store:false`, and array-form input; they exclude tools including image generation. Our editable SVG approach could fit text-based inference, but the API-key adapter cannot simply accept a ChatGPT token. A future adapter should implement the supported OAuth flow, eligibility/error handling, consent and revocation, then stream eligible inference. **This version implements mock, replay and API-key OpenAI only.** No browser automation, extracted ChatGPT cookies, borrowed Codex tokens, or impersonated API access is used.

OpenAI API implementation follows the [official quickstart](https://developers.openai.com/api/docs/quickstart).

## Experiment with each agent

Open **Agent playground**. Select a role and provider, edit the supplied JSON context, then click **Run**. Results are shown as JSON without changing any project. The sample includes all four agents' inputs so you can switch roles immediately.

Useful inputs:

| Agent ID | Context to change | Experiment |
|---|---|---|
| `director` | `name`, `messages` (`role` / `content`) | Add another user message with audience or tone constraints |
| `copywriter` | `brief`, optionally `copy` and `feedback` | Try a concise versus playful headline with OpenAI |
| `designer` | `brief`, `copy`, optionally `design`, `feedback` | Ask for a different palette; output includes SVG when brief/copy are supplied |
| `critic` | `brief`, `copy`, `design`, `metrics`, `revision` | Compare a high-contrast and low-contrast palette |

The isolated critic endpoint returns the provider's critique; workflow contrast enforcement and the one-revision loop belong to the orchestrator. Mock/replay deliberately use predictable responses; use OpenAI for semantic experimentation.

Use `/docs` to call `POST /api/agents/{agent}/run`, or PowerShell:

```powershell
$body = @{ provider = 'mock'; context = @{ brief = @{ title = 'Night Market'; details = 'Friday at 18:00' } } } | ConvertTo-Json -Depth 10
Invoke-RestMethod http://127.0.0.1:8000/api/agents/copywriter/run -Method Post -ContentType 'application/json' -Body $body
```

## Automated checks

```powershell
.\.venv\Scripts\python -m pytest -q
cd frontend
npm.cmd test
npm.cmd run build
```

Backend tests cover the complete mock and replay workflows, persistent reload/export, escaped SVG, approval gates, stale writes, provider failure rollback, exact recording/replay, contrast enforcement, one-revision budget, standalone agents and a stubbed official SDK request. Frontend tests cover editing approval fields, creating a project and standalone agent execution. The OpenAI adapter is tested with a stub; a paid live call requires your API key and is not part of automated checks.

With the server running, `python scripts/smoke.py` checks the actual HTTP service, built assets, complete mock workflow, SVG download, persistent reload and all four standalone agent endpoints. It creates a saved demo project. Initial verification: **13 backend tests and 3 frontend tests passed**, production build passed, HTTP smoke test passed, and npm audit reported **0 vulnerabilities**. Browser visual inspection was unavailable in the build session. Starlette currently emits a test-client deprecation warning for httpx; it does not affect these checks.

On this machine, Node dependency downloads required the Windows system certificate store: `$env:NODE_OPTIONS='--use-system-ca'` before npm commands. Certificate validation remains enabled.

The existing project directory and Git repository were retained. Runtime files, secrets, node modules, generated assets, recordings and databases are ignored by Git. `frontend/package-lock.json` pins frontend installs.
