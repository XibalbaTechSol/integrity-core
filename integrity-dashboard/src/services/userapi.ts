import { USERAPI_URL } from '../config';

// Mirrors integrity-userapi/app/schemas.py. JWT is kept in sessionStorage,
// not localStorage — deliberately short-lived, cleared when the tab closes.
const TOKEN_KEY = 'integrity_userapi_jwt';

const emitAuthChanged = () => {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('integrity-auth-changed'));
};

// Some browser/embedding contexts throw on any Storage access rather than returning null --
// getToken() is called directly from SettingsContext's render body (apiKeysAuthed), so an
// unguarded throw here takes down every route that provider wraps, not just an auth check.
export const getToken = (): string | null => {
    try {
        return sessionStorage.getItem(TOKEN_KEY);
    } catch {
        return null;
    }
};
const setToken = (token: string) => {
    try {
        sessionStorage.setItem(TOKEN_KEY, token);
    } catch {
        // Best-effort only -- see getToken's comment.
    }
    emitAuthChanged();
};
export const clearToken = () => {
    try {
        sessionStorage.removeItem(TOKEN_KEY);
    } catch {
        // Best-effort only -- see getToken's comment.
    }
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
    name?: string;
    photoURL?: string;
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
    me: async () => {
        const u = await request<UserResponse>('/me', {}, true);
        let localName: string | null = null;
        try {
            localName = localStorage.getItem(`integrity_name_${u.id}`);
        } catch {
            // Best-effort only -- see getToken's comment.
        }
        if (localName) u.name = localName;
        return u;
    },
    updateProfile: async (data: { name: string }) => {
        const u = await request<UserResponse>('/me', {}, true);
        try {
            localStorage.setItem(`integrity_name_${u.id}`, data.name);
        } catch {
            // Best-effort only -- see getToken's comment.
        }
        return { ...u, name: data.name };
    },
    listApiKeys: () => request<ApiKeyResponse[]>('/api-keys', {}, true),
    createApiKey: () => request<ApiKeyCreateResponse>('/api-keys', { method: 'POST' }, true),
    revokeApiKey: (id: string) => request<void>(`/api-keys/${id}`, { method: 'DELETE' }, true),
    myAgents: () => request<OwnedAgentResponse[]>('/me/agents', {}, true),
    addAgent: (agentDid: string) =>
        request<OwnedAgentResponse>('/me/agents', {
            method: 'POST',
            body: JSON.stringify({ agent_did: agentDid }),
        }, true),
    getWallet: () => request<{ app_wallet_address: string; balance: number }>('/me/wallet', {}, true),
    walletTransfer: (recipient_address: string, amount: number) =>
        request<{ status: string; new_balance: number }>('/me/wallet/transfer', {
            method: 'POST',
            body: JSON.stringify({ recipient_address, amount }),
        }, true),
};

export { UserApiError };
