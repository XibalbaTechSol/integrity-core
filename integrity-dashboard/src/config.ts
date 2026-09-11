export const ORACLE_URL = import.meta.env.VITE_ORACLE_URL || 'http://localhost:8080';
export const USERAPI_URL = import.meta.env.VITE_USERAPI_URL || 'http://localhost:8090';
export const BCC_MIDDLEWARE_URL = import.meta.env.VITE_BCC_MIDDLEWARE_URL || 'http://localhost:8000';
export const CHAIN_ID = Number(import.meta.env.VITE_CHAIN_ID) || 84532;
// xibalba-cortex's local_api.py (stdlib http.server, read-only) -- a separate local
// project, not part of this repo's own backend stack. Run it with:
//   .venv/bin/python -m xibalba_cortex.local_api --home ~/.hermes/xibalba-cortex \
//     --allowed-origin http://localhost:5173
export const GRAPH_MEMORY_URL = import.meta.env.VITE_GRAPH_MEMORY_URL || 'http://localhost:8420';
// Cortex local_api requires an explicit bearer token. Keep this opt-in so a
// production dashboard never silently sends a development credential.
export const GRAPH_MEMORY_TOKEN = import.meta.env.VITE_GRAPH_MEMORY_TOKEN || '';
// xibalba-shield's backend API (shield/backend/api.py — stdlib http.server). Run it with:
//   uv run python -m shield.backend.api --admin-token dev-shield-admin
export const SHIELD_BACKEND_URL = import.meta.env.VITE_SHIELD_BACKEND_URL || 'http://localhost:8765';
export const SHIELD_BACKEND_TOKEN = import.meta.env.VITE_SHIELD_BACKEND_TOKEN || 'dev-shield-admin';
// Shield tenants are control-plane namespaces, not agent DIDs. Keep the mapping
// deployment-configurable; falling back to the selected agent remains useful for
// isolated demo tenants but must never be mistaken for production identity mapping.
export const SHIELD_TENANT_ID = import.meta.env.VITE_SHIELD_TENANT_ID || '';
