# Shield Tier 3 Cloud Escalation (A2A Protocol)

## 1. Overview
The Shield Tier 3 Cloud Escalation protocol (A2A - Agent to Agent) defines the communication standard and operational lifecycle for escalating critical security events from local or edge tier agents to the Tier 3 cloud infrastructure. This protocol ensures high-fidelity, secure, and resilient transmission of escalation data.

## 2. Lifecycle of a Tier 3 Escalation
A Tier 3 escalation follows a strict state machine to ensure no data loss and proper handling of critical events.

1. **Detection & Triaging (Tier 1/2):** A local agent detects an anomaly or security event that exceeds its autonomous resolution capabilities or matches a Tier 3 escalation policy.
2. **Pre-Escalation Assessment:** The agent packages the event context, telemetry, and local state into an escalation envelope.
3. **Handshake Initiation:** The agent initiates a secure mutual authentication handshake with the Tier 3 endpoint.
4. **Payload Transmission:** Upon successful handshake, the escalation payload is transmitted.
5. **Acknowledgment (ACK):** The Tier 3 cloud service responds with an ACK containing an Escalation ID and initial instructions.
6. **Active Session:** The connection may remain open for bi-directional streaming of commands (from cloud) and ongoing telemetry (from agent).
7. **Resolution & Teardown:** Once the event is resolved or transferred entirely to cloud orchestration, the agent receives a termination signal, and the session is securely closed.

## 3. Security Handshake
Security is paramount. The A2A protocol mandates Mutual TLS (mTLS) 1.3 combined with application-layer payload signing.

### Handshake Sequence:
1. **mTLS Negotiation:** Standard TLS 1.3 handshake using short-lived agent certificates issued by the internal PKI.
2. **Challenge-Response:** The Tier 3 gateway issues a cryptographic challenge.
3. **Attestation:** The agent responds with a signed token that includes the challenge, its hardware trust anchor (e.g., TPM quote), and current security posture score.
4. **Session Key Establishment:** An ephemeral session key is derived for application-layer encryption (in addition to the transport layer TLS).

## 4. API Payloads
All payloads are structured in JSON, compressed via zstd, and encrypted at the application layer.

### 4.1 Escalation Request (Agent -> Cloud)
```json
{
  "protocol_version": "1.2",
  "escalation_type": "tier3",
  "agent_id": "agt-8a7b6c5d4e3f",
  "timestamp": "2026-08-07T18:45:00Z",
  "urgency": "CRITICAL",
  "event_summary": {
    "category": "malware_execution",
    "confidence_score": 98,
    "indicators": ["hash:12345", "ip:192.168.1.100"]
  },
  "context_blob_id": "blob-998877",
  "signature": "base64_encoded_signature_here"
}
```

### 4.2 Escalation Acknowledgment (Cloud -> Agent)
```json
{
  "status": "ACCEPTED",
  "escalation_id": "esc-tier3-20260807-001",
  "directive": {
    "action": "HOLD_AND_STREAM",
    "stream_endpoint": "wss://tier3.shield.internal/stream/esc-tier3-20260807-001"
  },
  "timestamp": "2026-08-07T18:45:01Z"
}
```
