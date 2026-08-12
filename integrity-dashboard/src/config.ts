export const ORACLE_URL = import.meta.env.VITE_ORACLE_URL || 'http://localhost:8080';
export const USERAPI_URL = import.meta.env.VITE_USERAPI_URL || 'http://localhost:8090';
export const BCC_MIDDLEWARE_URL = import.meta.env.VITE_BCC_MIDDLEWARE_URL || 'http://localhost:8000';
export const CHAIN_ID = Number(import.meta.env.VITE_CHAIN_ID) || 84532;
// xibalba-graph-memory's local_api.py (stdlib http.server, read-only) -- a separate local
// project, not part of this repo's own backend stack. Run it with:
//   .venv/bin/python -m xibalba_graph.local_api --home ~/.hermes/xibalba-graph-memory \
//     --allowed-origin http://localhost:5173
export const GRAPH_MEMORY_URL = import.meta.env.VITE_GRAPH_MEMORY_URL || 'http://localhost:8420';
// xibalba-shield's backend API (shield/backend/api.py — stdlib http.server). Run it with:
//   uv run python -m shield.backend.api --admin-token dev-shield-admin
export const SHIELD_BACKEND_URL = import.meta.env.VITE_SHIELD_BACKEND_URL || 'http://localhost:8765';
export const SHIELD_BACKEND_TOKEN = import.meta.env.VITE_SHIELD_BACKEND_TOKEN || 'dev-shield-admin';
