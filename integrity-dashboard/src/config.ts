export const ORACLE_URL = import.meta.env.VITE_ORACLE_URL || 'http://localhost:8080';
export const USERAPI_URL = import.meta.env.VITE_USERAPI_URL || 'http://localhost:8090';
export const BCC_MIDDLEWARE_URL = import.meta.env.VITE_BCC_MIDDLEWARE_URL || 'http://localhost:8000';
export const CHAIN_ID = Number(import.meta.env.VITE_CHAIN_ID) || 84532;
// xibalba-cortex's local_api.py (stdlib http.server, read-only) -- a separate local
// project, not part of this repo's own backend stack. Run it with:
//   .venv/bin/python -m xibalba_cortex.local_api --home ~/.hermes/xibalba-cortex \
//     --allowed-origin http://localhost:5173
export const GRAPH_MEMORY_URL = import.meta.env.VITE_GRAPH_MEMORY_URL || 'http://localhost:8420';
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
