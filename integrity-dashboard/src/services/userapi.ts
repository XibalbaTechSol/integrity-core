import { USERAPI_URL } from '../config';

// Mirrors integrity-userapi/app/schemas.py. JWT is kept in sessionStorage,
// not localStorage — deliberately short-lived, cleared when the tab closes,
// consistent with how the SDK/CLI treat credentials as ephemeral rather than
// durably persisted secrets.
const TOKEN_KEY = 'integrity_userapi_jwt';

// Fired on every auth transition (login, register, logout) so the app shell
// (Sidebar's real-session profile) can refresh without a full reload.
// sessionStorage's native 'storage' event only fires in OTHER tabs, never the
// one that made the change, so this same-tab custom event is required.
const emitAuthChanged = () => {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('integrity-auth-changed'));
};

export const getToken = (): string | null => sessionStorage.getItem(TOKEN_KEY);
const setToken = (token: string) => {
    sessionStorage.setItem(TOKEN_KEY, token);
    emitAuthChanged();
};
export const clearToken = () => {
    sessionStorage.removeItem(TOKEN_KEY);
    emitAuthChanged();
};

export interface TokenResponse {
    access_token: string;
    token_type: string;
}

export interface UserResponse {
    id: string;
    email: string;
    created_at: string;
}

export interface ApiKeyResponse {
    id: string;
    ais_trust_ceiling: number;
    revoked_at: string | null;
    created_at: string;
}

export interface ApiKeyCreateResponse extends ApiKeyResponse {
    raw_key: string;
}

export interface OwnedAgentResponse {
    agent_did: string;
    added_at: string;
    live_data: Record<string, unknown> | null;
    error: string | null;
}

class UserApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

async function request<T>(path: string, options: RequestInit = {}, authed = false): Promise<T> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json', ...(options.headers as Record<string, string>) };
    if (authed) {
        const token = getToken();
        if (!token) {
            throw new UserApiError(401, 'Not authenticated');
        }
        headers['Authorization'] = `Bearer ${token}`;
    }
    const res = await fetch(`${USERAPI_URL}${path}`, { ...options, headers });
    if (!res.ok) {
        throw new UserApiError(res.status, `userapi request failed: ${res.status} ${path}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
}

export const userapi = {
    register: async (email: string, password: string) => {
        const token = await request<TokenResponse>('/auth/register', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        setToken(token.access_token);
        return token;
    },
    login: async (email: string, password: string) => {
        const token = await request<TokenResponse>('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        setToken(token.access_token);
        return token;
    },
    logout: () => clearToken(),
    me: () => request<UserResponse>('/me', {}, true),
    listApiKeys: () => request<ApiKeyResponse[]>('/api-keys', {}, true),
    createApiKey: () => request<ApiKeyCreateResponse>('/api-keys', { method: 'POST' }, true),
    revokeApiKey: (id: string) => request<void>(`/api-keys/${id}`, { method: 'DELETE' }, true),
    myAgents: () => request<OwnedAgentResponse[]>('/me/agents', {}, true),
    addAgent: (agentDid: string) =>
        request<OwnedAgentResponse>('/me/agents', {
            method: 'POST',
            body: JSON.stringify({ agent_did: agentDid }),
        }, true),
};

export { UserApiError };
