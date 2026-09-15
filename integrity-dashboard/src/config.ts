export const ORACLE_URL = import.meta.env.VITE_ORACLE_URL || 'http://localhost:8080';
export const USERAPI_URL = import.meta.env.VITE_USERAPI_URL || 'http://localhost:8090';
export const BCC_MIDDLEWARE_URL = import.meta.env.VITE_BCC_MIDDLEWARE_URL || 'http://localhost:8000';
export const CHAIN_ID = Number(import.meta.env.VITE_CHAIN_ID) || 84532;
// xibalba-cortex's local_api.py (stdlib http.server, read-only) -- a separate local
// project, not part of this repo's own backend stack. Run it with:
//   .venv/bin/python -m xibalba_cortex.local_api --home ~/.hermes/xibalba-cortex \
//     --allowed-origin http://localhost:5173
// In local development, route through Vite's loopback-only proxy so the browser never receives
// the Cortex operator token. Production deployments must provide their own authenticated origin.
//
// NOTE (2026-09-15): cookie-based auth (credentials: 'include' in graphMemory.ts) cannot work
// against Cortex from this dashboard no matter which Cortex origin/port is targeted here. This
// dashboard is itself served over plain http://localhost:5173; Cortex's session cookie is
// HttpOnly/Secure/SameSite=Strict, set while browsing Cortex's own https://localhost:9443.
// Under schemeful same-site (the modern browser default), the *initiating page's* scheme is
// what's compared against the cookie's site -- http://localhost:5173 vs the cookie's https
// site are cross-site regardless of the fetch target's scheme, so SameSite=Strict withholds
// the cookie. Verified empirically: fetching https://localhost:9443/api/status with
// credentials:'include' from an http://localhost:5173 page returns 401; the identical fetch
// from an https://localhost:9443 page returns 200. Fixing this needs either serving this
// dashboard over HTTPS too, or switching Cortex calls to Bearer-token auth (as shieldBackend.ts
// already does via SHIELD_BACKEND_TOKEN) instead of cookies -- not done here, scope TBD.
export const GRAPH_MEMORY_URL = import.meta.env.VITE_GRAPH_MEMORY_URL || (import.meta.env.DEV ? '/cortex-api' : 'http://localhost:8420');
// xibalba-shield's backend API (shield/backend/api.py — stdlib http.server). Run it with:
//   uv run python -m shield.backend.api --admin-token dev-shield-admin
export const SHIELD_BACKEND_URL = import.meta.env.VITE_SHIELD_BACKEND_URL || 'http://localhost:8765';
export const SHIELD_BACKEND_TOKEN = import.meta.env.VITE_SHIELD_BACKEND_TOKEN || 'dev-shield-admin';
// A DIFFERENT server than SHIELD_BACKEND_URL -- xibalba-shield's real root+eBPF Flask demo
// (slm_training/app.py), routes shaped /api/launch, /api/simulate, /api/status/:pid, no admin
// token. Port corrected 2026-08-28: app.py's own `app.run(..., port=5050)` -- the previous
// default (5000) could never reach it even when the demo was running. Not the same as
// SHIELD_BACKEND_URL, whose routes (/api/shield/*) are shaped differently.
export const SHIELD_SIM_BACKEND_URL = import.meta.env.VITE_SHIELD_SIM_BACKEND_URL || 'http://localhost:5050';
