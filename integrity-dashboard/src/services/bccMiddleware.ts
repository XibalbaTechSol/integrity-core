import { BCC_MIDDLEWARE_URL } from '../config';

// Real client for bcc_middleware's admin endpoints. Only one real, narrow
// runtime-config surface exists today: the clinical-agent allowlist OPA data
// document (bcc.rego's `data.clinical_allowlist.agents` extension point) —
// see bcc_middleware/app/main.py's get/set_clinical_allowlist. Everything else
// about policy behavior (thresholds, new rule types) requires editing the
// read-only-mounted .rego files and redeploying the opa container; there is
// no admin surface for that, and this client doesn't pretend otherwise.

class BccMiddlewareError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const res = await fetch(`${BCC_MIDDLEWARE_URL}${path}`, {
        ...options,
        headers: { 'Content-Type': 'application/json', ...(options.headers as Record<string, string>) },
    });
    if (!res.ok) {
        throw new BccMiddlewareError(res.status, `bcc_middleware request failed: ${res.status} ${path}`);
    }
    return res.json();
}

export const bccMiddleware = {
    getClinicalAllowlist: () => request<{ agents: string[] }>('/v1/admin/clinical-allowlist'),
    setClinicalAllowlist: (agents: string[]) =>
        request<{ agents: string[] }>('/v1/admin/clinical-allowlist', {
            method: 'PUT',
            body: JSON.stringify({ agents }),
        }),
};

export { BccMiddlewareError };
