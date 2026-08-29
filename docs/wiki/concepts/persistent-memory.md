---
title: Persistent Memory Bridge
created: 2026-07-30
updated: 2026-07-30
type: concept
tags: [architecture, sdk, primitive]
confidence: high
---

# Persistent Memory Configuration Guide

The Persistent Memory Bridge allows agents to anchor their localized memory states cryptographically to the blockchain. Agents use this architecture to prove that their internal knowledge base (e.g. vector databases, key-value stores) remains untampered and mathematically verifiable.

## Table of contents

- [1. The TrustVault Primitive](#1-the-trustvault-primitive)
- [2. Pluggable Memory Backends](#2-pluggable-memory-backends)
  - [JSONLBackend (Default)](#jsonlbackend-default)
  - [RAGBackend (Vector Databases)](#ragbackend-vector-databases)
  - [GraphBackend (Relational/Knowledge Graphs)](#graphbackend-relational-knowledge-graphs)
- [3. CLI Configuration](#3-cli-configuration)
- [4. MCP Agent Integration](#4-mcp-agent-integration)

## 1. The `TrustVault` Primitive

Agents manage memory states via the `TrustVault` context manager exposed in `integrity-sdk` and `integrity-cli`.

**Features:**
- **Pre-flight Checks**: Before a session starts, `TrustVault` fetches the agent's on-chain `StateAnchor` contract. It reads `currentRoot()` and verifies it matches the local backend's derived `state_root`. Any drift (from tampering or accidental desynchronization) immediately aborts the session.
- **Session Commits**: After interacting, the session compiles context into a `session_data` object, appends it to the backend, and calculates the new root.
- **On-chain Anchoring**: The agent then calls `anchorRoot()` on its `StateAnchor` contract with the new root.

## 2. Pluggable Memory Backends

The SDK provides an adapter pattern (`MemoryBackend`) allowing agents to use any underlying storage architecture.

### JSONLBackend (Default)
**Use Case**: Simple append-only logs for linear conversational history.
**Configuration**:
```python
from pathlib import Path
from integrity_sdk.memory import JSONLBackend, TrustVault

backend = JSONLBackend(storage_path=Path("~/.integrity-cli/vault/xibalba/memory_log.jsonl"))
vault = TrustVault(agent_did="did:integrity:...", backend=backend)
```
*Root Calculation*: A sequential keccak256 hash chain of each line.

### RAGBackend (Vector Databases)
**Use Case**: Dense retrieval architectures for high-dimensional semantic search (e.g., Pinecone, Weaviate, Qdrant, Chroma).
**Configuration**:
```python
from integrity_sdk.memory import RAGBackend, TrustVault

# Supply standard connection strings or endpoint URLs
backend = RAGBackend(connection_string="http://localhost:8080/vector_db")
vault = TrustVault(agent_did="did:integrity:...", backend=backend)
```
*Root Calculation*: A Merkle Root of all document chunk hashes stored in the collection. The `RAGBackend` queries the database for the sorted chunk list and builds the Merkle Tree client-side to derive the root.

### GraphBackend (Relational/Knowledge Graphs)
**Use Case**: Graph databases representing complex entity relations (e.g., Neo4j).
**Configuration**:
```python
from integrity_sdk.memory import GraphBackend, TrustVault

backend = GraphBackend(connection_string="bolt://localhost:7687")
vault = TrustVault(agent_did="did:integrity:...", backend=backend)
```
*Root Calculation*: Canonical serialization of nodes and edges, hashed via keccak256.

## 3. CLI Configuration

Users can also synchronize and anchor memory directly via the terminal:

```bash
# Sync a transcript into the default JSONLBackend and anchor on-chain
integrity vault sync <agent_name> --transcript /path/to/transcript.jsonl
```

## 4. MCP Agent Integration

Agents connected via the Model Context Protocol (MCP) use the `integrity_commit_memory` tool provided by the `integrity-sdk` MCP server. The harness passes the session summary, and the server handles `TrustVault` instantiation, pre-flight checking, and on-chain anchoring autonomously.
