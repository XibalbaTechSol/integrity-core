export interface ShieldDevice {
    tenant_id: string;
    device_id: string;
    device_role: string;
    policy_version: string | null;
    policy_hash: string | null;
    last_seen_at: string | null;
    enrolled_at: string;
    agent_label?: string;
}

export interface ShieldDecisionAction {
    action: string;
    severity?: string;
    reason?: string;
}

export interface ShieldDecisionRecord {
    class?: string;
    device_id?: string;
    time?: string;
    event_ref?: { class?: string; event_id?: string };
    rule?: { rule_id?: string; name?: string; version?: string };
    decision?: ShieldDecisionAction;
    export?: { attempted?: boolean; event_exported?: boolean; decision_exported?: boolean; authorized?: boolean };
    policy?: { version?: string; hash?: string };
    synthetic?: boolean;
}

export interface ShieldDecision {
    decision: ShieldDecisionRecord;
    received_at: string;
}

export interface ShieldDashboardSummary {
    tenant_id: string;
    device_count: number;
    decisions_by_action: Record<string, number>;
    devices: ShieldDevice[];
    latest_decisions: ShieldDecision[];
    latest_metrics: Record<string, unknown> | null;
    integrations: ShieldIntegration[];
    exporter_status: Array<{ device_id: string; status: { did_registered?: boolean; oracle_readback?: unknown } }>;
}

export interface ShieldExporterStatus {
    device_id: string;
    did_registered: boolean;
    bcc_middleware: string;
    oracle_readback: string;
    synthetic?: boolean;
    updated_at?: string;
}

export interface ShieldIntegration {
    integration_id: string;
    kind: string;
    config: Record<string, unknown>;
    created_at?: string;
}

export interface ShieldEnrollment {
    tenant_id: string;
    device_id: string;
    device_token: string;
    device_config: Record<string, unknown>;
}

export interface ShieldPolicyBundle {
    policy_version: string;
    policy_hash: string;
    rules: number;
}

export interface ShieldSeedResult {
    tenant_id: string;
    device_id: string;
    device_token: string;
    device_config: Record<string, unknown>;
    policy_hash: string;
    seeded_decisions: number;
}
