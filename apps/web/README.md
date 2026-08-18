# SpecProof Web (apps/web)

React 18 + Vite 5 + TypeScript SPA for the SpecProof dashboard.

## Commands

- npm install      install dependencies
- npm run dev      dev server on :5173 (proxies /api, /jobs, /health to localhost:8000)
- npm run build    typecheck (tsc) + production build into dist/
- npm run preview  serve the production build locally

## Serving

The FastAPI server (api/server.py) serves apps/web/dist at / when the build
exists (SPA fallback to index.html for deep links); otherwise it falls back
to the legacy static dashboard at /dashboard.

## Auth

The API key is kept in sessionStorage and sent as X-API-Key on every API
call. The SSE progress stream passes the key as a query parameter because
EventSource cannot set headers (api/auth.py accepts X-API-Key, Bearer, or
api_key/key query parameter, constant-time compared).

## Zero external runtime services

The SPA talks only to the SpecProof FastAPI backend. No CDN, no external
fonts, no third-party UI runtime.
