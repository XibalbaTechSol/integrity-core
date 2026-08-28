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
    invocation_id?: string;
    class?: string;
    device_id?: string;
    time?: string;
    event_ref?: { class?: string; event_id?: string };
    rule?: { rule_id?: string; name?: string; version?: string };
    decision?: ShieldDecisionAction;
    export?: { attempted?: boolean; event_exported?: boolean; decision_exported?: boolean; authorized?: boolean; invocation_id?: string };
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

// shield/backend/store.py's enforcement_outcomes table -- "what actually happened when a
// decision's chosen action was carried out" (forward-link counterpart to a ShieldDecision,
// keyed by the same event_id). Real per-device execution results, not a decision itself.
export interface ShieldEnforcementOutcome {
    received_at: string;
    outcome: {
        event_id: string;
        agent_id?: string;
        action: string;
        completed: boolean;
        escalated: boolean;
        [key: string]: unknown;
    };
}

// shield/backend/store.py's detection_quality table -- Shield's own detection-rate/precision/
// false-positive/containment-latency scorecard per device, computed from real recorded
// decisions, not a fabricated demo metric.
export interface ShieldDetectionQuality {
    device_id: string;
    received_at: string;
    quality: {
        aggregate: {
            shield_adr: number | null;
            precision: number | null;
            blocking_false_positive_rate: number | null;
            mean_time_to_contain_sec: number | null;
        };
        synthetic?: boolean;
        [key: string]: unknown;
    };
}

export interface ShieldSeedResult {
    tenant_id: string;
    device_id: string;
    device_token: string;
    device_config: Record<string, unknown>;
    policy_hash: string;
    seeded_decisions: number;
}
