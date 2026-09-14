import { USERAPI_URL } from '../config';

// The real credential is an HttpOnly session cookie (see integrity-userapi's
// app/security.py session_cookie_header) -- JS cannot read it, and every request below
// sends it automatically via `credentials: 'include'`. AUTHED_KEY is NOT a credential: it's
// a same-tab-only "did we last see a successful login/register" marker, purely so the UI
// (SettingsContext.apiKeysAuthed, TokenWallet, DashboardContext) can decide what to render
// without an extra round trip. Actual authorization is always the server's call: any 401
// from `request()` clears this marker, so it can never claim "authed" once the server
// disagrees. Mirrors Cortex's own viewer, which keeps a similar non-credential
// sessionStorage marker alongside its HttpOnly cookie.
const AUTHED_KEY = 'integrity_userapi_authed';

const emitAuthChanged = () => {
    if (typeof window !== 'undefined') window.dispatchEvent(new Event('integrity-auth-changed'));
};

// Some browser/embedding contexts throw on any Storage access rather than returning null --
// getToken() is called directly from SettingsContext's render body (apiKeysAuthed), so an
// unguarded throw here takes down every route that provider wraps, not just an auth check.
export const getToken = (): string | null => {
    try {
        return sessionStorage.getItem(AUTHED_KEY);
    } catch {
        return null;
    }
};
const setToken = () => {
    // Only emit on an actual transition -- meIfSignedIn() calls this every time it
    // successfully re-confirms an already-known session, and emitting unconditionally would
    // re-trigger DashboardContext's 'integrity-auth-changed' listener, which calls
    // meIfSignedIn() again, forever.
    if (getToken() === '1') return;
    try {
        sessionStorage.setItem(AUTHED_KEY, '1');
    } catch {
        // Best-effort only -- see getToken's comment.
    }
    emitAuthChanged();
};
export const clearToken = () => {
    if (getToken() === null) return;
    try {
        sessionStorage.removeItem(AUTHED_KEY);
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
    // `authed` no longer gates on a locally-held token (there is none to hold -- the cookie
    // is HttpOnly). It's still useful as an early, no-network "we know we're signed out"
    // check, since AUTHED_KEY is cleared on every 401 below.
    if (authed && !getToken()) {
        throw new UserApiError(401, 'Not authenticated');
    }
    const res = await fetch(`${USERAPI_URL}${path}`, { ...options, headers, credentials: 'include' });
    if (res.status === 401) clearToken();
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
        setToken();
        return token;
    },
    login: async (email: string, password: string) => {
        const token = await request<TokenResponse>('/auth/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        setToken();
        return token;
    },
    // Revokes the session server-side (see integrity-userapi's /auth/logout, which now also
    // clears the cookie) before dropping the local marker -- previously this only cleared
    // local state and never told the server, so the JWT stayed valid until it expired.
    logout: async () => {
        try {
            await request<void>('/auth/logout', { method: 'POST' }, true);
        } finally {
            clearToken();
        }
    },
    // Deliberately does not gate on the local "authed" marker (unlike other `authed` calls)
    // and instead always asks the server: the marker is per-tab sessionStorage, but the real
    // credential is a cookie shared across tabs, so a fresh tab with a valid session cookie
    // must still be able to bootstrap as signed-in. Syncs the marker on success so later
    // same-tab calls (listApiKeys, etc.) can cheaply pre-check without a network round trip.
    meIfSignedIn: async (): Promise<UserResponse | null> => {
        try {
            const u = await request<UserResponse>('/me', { credentials: 'include' } as RequestInit);
            setToken();
            let localName: string | null = null;
            try {
                localName = localStorage.getItem(`integrity_name_${u.id}`);
            } catch {
                // Best-effort only -- see getToken's comment.
            }
            if (localName) u.name = localName;
            return u;
        } catch {
            clearToken();
            return null;
        }
    },
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
