# SpecProof Agent Console (VS Code extension)

First version of the VS Code extension for the SpecProof agent console API
(`/agent/jobs`, see `api/routes/agent_console.py`). Minimal but functional:
a sidebar console for agent jobs plus a status bar.

## Features

- **Agent Tasks** sidebar — lists jobs from `GET /agent/jobs` with status
  icons, plan step counts, event and approval counts. Clicking an entry makes
  it the current job.
- **Plan (JSON Tree)** sidebar — renders the current job's `plan` document
  as a JSON tree (generic object/array walk). Each plan step shows its status
  and, after a decision, its approval record. Steps can be approved or
  rejected from the context menu.
- **Approve / Cancel commands** — plan approve/reject, final gate
  approve/reject and job cancel, all through
  `POST /agent/jobs/{id}/approve` and `POST /agent/jobs/{id}/cancel`.
- **Changed Files** sidebar — `GET /agent/jobs/{id}/diff` populates the
  change-bundle file list with hunk summaries; clicking a file opens a
  read-only unified diff document.
- **Status bar** — shows the current job state
  (`SpecProof: EXECUTING · current job`); clicking it jumps to the Agent Tasks
  view. The task list is polled while that view is visible
  (`specproofAgent.pollIntervalSeconds`).

## Requirements

- VS Code 1.95 or newer.
- Node.js 18+ (verified with Node 24) for building and unit tests.
- The SpecProof API server running locally (default `http://127.0.0.1:8000`).

## Run the API server

```powershell
cd D:\experim\specproof-clean-clone-gate
$env:SPECPROOF_API_KEY = "replace_me"   # job endpoints refuse to run without a key
python -m api.server                    # uvicorn on 0.0.0.0:8000
```

Agent jobs use the in-memory store by default (`SPECPROOF_AGENT_JOBS_URL`
empty). The console never accepts requests without a matching key, so set the
same value in the extension settings below.

## Run the extension

```powershell
cd ide\vscode
npm install
npm run compile        # emits out/extension.js
npm test               # vitest unit tests for the client layer
npm run typecheck      # tsc --noEmit for extension sources
npm run typecheck:test # tsc --noEmit for test sources
```

Then open the `ide/vscode` folder in VS Code and press **F5**
("Run Extension", `.vscode/launch.json`) — an Extension Development Host
window opens with the SpecProof Agent activity-bar icon.

## Configure

File → Preferences → Settings, search for "SpecProof":

- `specproofAgent.apiBaseUrl` — API base URL (default
  `http://127.0.0.1:8000`).
- `specproofAgent.apiKey` — value sent as the `X-API-Key` header; must
  match the server's `SPECPROOF_API_KEY` (use `replace_me` in
  development, never commit a real key).
- `specproofAgent.pollIntervalSeconds` — task list refresh cadence
  (default 5, minimum 1).

## Try it

1. Start the API server (above) and set the API key in the extension settings.
2. In the Agent Tasks view, click **Create Agent Job…** and enter a repo path
   and spec text. Leave both empty to run the bundled demo task with
   `auto_start=true`.
3. When the plan shows up (status `AWAITING_APPROVAL`), right-click the job
   → **Approve Plan** (or approve/reject single steps in the plan view).
4. Watch the status bar move through `EXECUTING`, then open **Changed
   Files** and click a file to read the unified diff.

## Layout

- `src/client.ts` — pure HTTP client and wire types for `/agent/jobs`
  (no `vscode` imports; unit-tested).
- `src/diffText.ts` — pure unified-diff text renderer (unit-tested).
- `src/jobsProvider.ts`, `src/planProvider.ts`, `src/diffProvider.ts` —
  tree views plus the virtual diff document provider.
- `src/extension.ts` — activation, commands, polling, status bar.
- `test/` — vitest unit tests for the pure layers.

## Gates

- `npx tsc --noEmit` (extension sources)
- `npx tsc --noEmit -p tsconfig.test.json` (test sources)
- `npx vitest run` (client layer + diff renderer)
- no real API key literals and no leftover placeholder markers anywhere
  under `ide/vscode`.
