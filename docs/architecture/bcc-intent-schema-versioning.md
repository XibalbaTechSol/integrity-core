# BCC Intent Schema Versioning Specification

## 1. Introduction
This document outlines the protocol design specification for BCC (Blockchain Communication Channel) intent schema versioning within the INTEGRITY ecosystem. It details the mechanisms for versioning, upgrading, and validating intents across different components and participants in the network.

## 2. Versioning Strategy
Intents in the INTEGRITY ecosystem follow Semantic Versioning (SemVer) principles (MAJOR.MINOR.PATCH) for schema definitions.

*   **MAJOR**: Incremented for incompatible schema changes (e.g., removing a required field, changing data types of existing fields).
*   **MINOR**: Incremented for backward-compatible functionality additions (e.g., adding a new optional field).
*   **PATCH**: Incremented for backward-compatible bug fixes (e.g., updating descriptions, fixing typos in metadata).

Every intent payload must explicitly declare its schema version.

```json
{
  "$schema": "https://integrity.network/schemas/bcc-intent/v1.2.0.json",
  "intent_id": "...",
  "version": "1.2.0",
  "type": "transfer",
  "payload": { ... }
}
```

## 3. Schema Upgrades

### 3.1. Proposing Upgrades
Upgrades to the BCC intent schema are proposed through the INTEGRITY Improvement Proposal (IIP) process. Proposals must include:
*   The updated JSON schema.
*   A detailed changelog.
*   Migration strategies for legacy intents.

### 3.2. Deprecation and Sunset
When a MAJOR schema version is introduced, the previous MAJOR version enters a deprecation phase. 
*   **Deprecation Phase**: Nodes accept both the new and the deprecated versions.
*   **Sunset Phase**: After a predefined blocks/time duration, nodes reject the deprecated version.

## 4. Cross-Ecosystem Validation

### 4.1. Intent Routing and Validation
When an intent is broadcasted to the network, validators perform the following steps:
1.  **Version Extraction**: Read the `version` field from the intent envelope.
2.  **Schema Resolution**: Fetch the corresponding schema definition from the decentralized schema registry.
3.  **Payload Validation**: Validate the intent payload against the retrieved schema.
4.  **Forwarding**: If validation succeeds, forward the intent to relevant solvers/relayers.

### 4.2. Forward and Backward Compatibility
*   **Solvers**: Must be capable of processing multiple active schema versions.
*   **Relayers**: Only route intents that pass schema validation for supported versions.

## 5. Decentralized Schema Registry
The schema definitions are stored in an on-chain registry smart contract, ensuring immutability and transparency. Validators query this registry to cache active schemas for fast validation.
