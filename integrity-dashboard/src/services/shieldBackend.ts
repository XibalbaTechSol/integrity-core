import { SHIELD_BACKEND_URL, SHIELD_BACKEND_TOKEN } from '../config';

// Client for xibalba-shield's backend API (shield/backend/api.py — stdlib http.server,
// localhost:8765 by default). Admin routes require Bearer token. Device routes require
// per-device tokens issued during enrollment.

import type {
    ShieldDashboardSummary,
    ShieldDevice,
    ShieldEnrollment,
    ShieldExporterStatus,
    ShieldIntegration,
    ShieldSeedResult,
} from '../types/shield';

export type {
    ShieldDashboardSummary,
    ShieldDecision,
    ShieldDecisionAction,
    ShieldDecisionRecord,
    ShieldDevice,
    ShieldEnrollment,
    ShieldExporterStatus,
    ShieldIntegration,
    ShieldPolicyBundle,
    ShieldSeedResult,
} from '../types/shield';

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

async function adminGet<T>(path: string, params?: Record<string, string>, token = SHIELD_BACKEND_TOKEN): Promise<T> {
    const url = new URL(`${SHIELD_BACKEND_URL}${path}`);
    if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
    const response = await fetch(url.toString(), {
        headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({ error: response.statusText }));
        throw new Error(body.error ?? `shield-backend request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
}

async function adminPost<T>(path: string, payload: Record<string, unknown>, token = SHIELD_BACKEND_TOKEN): Promise<T> {
    const response = await fetch(`${SHIELD_BACKEND_URL}${path}`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => ({ error: response.statusText }));
        throw new Error(body.error ?? `shield-backend request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// API client — mirrors Shield backend's full route surface
// ---------------------------------------------------------------------------

export const shieldBackend = {
    // Health check (no auth)
    health: () =>
        fetch(`${SHIELD_BACKEND_URL}/api/shield/health`)
            .then(r => r.json() as Promise<{ ok: boolean; service: string }>),

    // Admin read routes
    dashboardSummary: (tenantId: string, token = SHIELD_BACKEND_TOKEN) =>
        adminGet<ShieldDashboardSummary>('/api/shield/dashboard-summary', { tenant_id: tenantId }, token),
    listDevices: (tenantId: string) =>
        adminGet<{ devices: ShieldDevice[] }>('/api/shield/devices', { tenant_id: tenantId }),
    getDevice: (tenantId: string, deviceId: string) =>
        adminGet<ShieldDevice>(`/api/shield/devices/${encodeURIComponent(deviceId)}`, { tenant_id: tenantId }),
    exporterStatus: (tenantId: string) =>
        adminGet<{ exporter_status: ShieldExporterStatus[] }>('/api/shield/exporter-status', { tenant_id: tenantId }),
    integrations: (tenantId: string) =>
        adminGet<{ integrations: ShieldIntegration[] }>('/api/shield/integrations', { tenant_id: tenantId }),

    // Admin write routes
    enrollDevice: (payload: { tenant_id: string; device_id: string; device_role?: string }, token?: string) =>
        adminPost<ShieldEnrollment>('/api/shield/enroll', payload, token),
    seedDemo: (payload: { tenant_id: string } | string, token = SHIELD_BACKEND_TOKEN) =>
        adminPost<ShieldSeedResult>('/api/shield/demo/seed', typeof payload === 'string' ? { tenant_id: payload } : payload, token),
    putIntegration: (payload: { tenant_id: string; kind: string; integration_id?: string; config?: Record<string, unknown> }, token?: string) =>
        adminPost<{ ok: boolean; integration_id: string }>('/api/shield/integrations', payload, token),
};
