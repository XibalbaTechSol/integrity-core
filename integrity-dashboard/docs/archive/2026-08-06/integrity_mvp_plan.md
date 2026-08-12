# Integrity MVP — Product & Architecture Blueprint

This document defines the extensive product scope, visual design principles, technical architecture, and implementation roadmap for `integrity-mvp`. It is maintained as a separate public frontend repository, but it is not a standalone system: it consumes the contracts and backend services from `INTEGRITY-LATEST` and presents endpoint-security data and controls from `xibalba-shield`.

The dependency graph is `integrity-mvp -> xibalba-shield -> INTEGRITY-LATEST`, plus direct
`integrity-mvp -> INTEGRITY-LATEST` calls for Oracle, user API, BCC middleware, and chain data.
Shield is built on the protocol rather than alongside a second trust backend: its
`integrity-sdk` exporter signs security decisions and submits them to INTEGRITY-LATEST. Neither
backend depends on the MVP frontend, and INTEGRITY-LATEST does not depend on Shield.

## Audit status — 2026-08-06

The current status ledger is [`docs/audits/2026-08-06-status.md`](docs/audits/2026-08-06-status.md). Mark implementation tasks `DONE` only when the repository has reproducible evidence; features that depend on live INTEGRITY-LATEST services, chain deployments, or Shield evidence remain integration-dependent until directly verified.

---

## 1. Product Vision & Value Proposition

The MVP bridges the gap between cryptographic telemetry (ZK proofs, TEE attestations, AIS scores) and real-world user experiences. 
*   **Investors:** View real-time economic flywheels. Staking $ITK, slashing mechanics, decentralized capital allocation via `A2ACapitalPool`, and live prediction markets via `IntegrityMarket` clones.
*   **Developers:** Access interactive Smart Contract IDEs, real-time MCP (Model Context Protocol) telemetry streams, and agent registration flows to connect custom AI agents to the Integrity Protocol.
*   **Enterprise / Healthcare:** Demonstrate true regulatory compliance (HIPAA) with mathematically proven Guardrails and on-chain Business Associate Agreements via the Integrity Health vertical.
*   **Security Teams:** Utilize Xibalba Shield, the dedicated agent security platform, to monitor, red-team, and enforce real-time bounds on autonomous systems.

---

## 2. Visual Design & Customizability

*   **Aesthetic Core:** Deep dark mode inspired by OpenAI, Perplexity, and LangSmith. Slate and deep navy backgrounds accented with glowing neon typography (gold for primary actions, emerald for verified states, red for slashing/drift).
*   **Notion-Style Modularity:** Custom drag-and-drop dashboard grids and block-based expandable tables.

---

## 3. Global Context: The Agent Fleet Selector

A core tenet of the MVP is managing a *fleet* of agents. The UI relies on a global context selector.
*   **Global Agent Switcher:** A prominent dropdown/selector (configurable in placement) that allows the user to instantly switch context between different agents in their registered fleet (e.g., switching from `TradingBot_v2` to `CodeReviewer_X`).
*   **Dynamic Reactivity:** Changing the globally selected agent instantly re-fetches and re-renders data across the Dashboard, AIS, Intelligence, Health, Shield, and Financial pages to reflect only that specific agent's telemetry.

---

## 4. Dedicated Page Architecture & Concrete Implementations

The MVP application is structured around the following core, dedicated routing paths, pulling
from the real `INTEGRITY-LATEST` backbone and, for endpoint-security workflows, Xibalba Shield.

### A. Dashboard (`/dashboard`)
*   **Purpose:** The central command center and aggregate view.
*   **Features:** Customizable Notion-style layout. Users can pin high-level widgets from other pages (e.g., a mini AIS sparkline, recent tool errors, or current ITK yield) onto a grid.
*   **Performance Analytics:** Alongside AIS, display real-time tracking of token costs, total latency, and error rates per agent to provide a complete operational picture.

### B. Identity & XNS Registry (`/identity`)
*   **Purpose:** Agent claiming, onboarding, and domain management.
*   **Implementation Details:**
    *   **Onboarding Wizard:** Generate DIDs (secp256k1) and connect MCP endpoints. This triggers transactions to the real `XibalbaAgentRegistry` on Base Sepolia.
    *   **XNS Registry:** Search, bid on, and mint human-readable `.xibalba` domains (ERC-721).
    *   **Tier Status:** Visual indicators of the Identity Verification Ceiling clamp (Tier 0: 300 Max AIS, Tier 1: 600, Tier 2: 850, Tier 3: 1000).

### C. AIS Metrics (`/ais`)
*   **Purpose:** Deep dive into the Agentic Integrity Score (Tri-Metric AIS v8.3).
*   **Implementation Details:**
    *   Visualizes the exact geometric volume formula computed by the `integrity-oracle/scoring-core`: `AIS = (S_entropy^0.30 * S_grounding^0.30 * S_sacrifice^0.20 * S_compliance^0.20) * ZK_boost`.
    *   **ZK Boost Indicator:** Highlights when the score receives the `1.15x` multiplier due to a valid Barretenberg Zero-Knowledge proof (`bb verify`) being submitted.

### D. Intelligence, Telemetry & Cryptographic Lineage (`/intelligence`)
*   **Purpose:** Complete observability into agent execution.
*   **Implementation Details & Advanced Features:**
    *   **Interactive Agent Graph:** A node-based visual graph mapping application flows (RAG retrievals, self-looping).
    *   **NOVEL FEATURE: The "Merkle Lens" Explorer:** 
        *   Interactive Cryptographic Unfolding of batched telemetry roots.
        *   Visual Data Derivation Mapping via SHA-256 animations.
        *   Proof-of-Inference connections linking Merkle Roots to Noir/Barretenberg ZK Circuit inputs.

### E. Integrity Health (HIPAA / Healthcare Vertical) (`/health`)
*   **Purpose:** The flagship enterprise vertical proving the protocol works in heavily regulated industries, achieving feature parity with leading Web2 healthcare AI platforms (like Hippocratic AI).
*   **Implementation Details & Parity Features:**
    *   **SmartBAA Escrow UI:** Cryptographic Business Associate Agreements. While Web2 competitors use paper BAAs, Integrity Health uses `SmartBAAFactory` to lock up $ITK as collateral for instant, verifiable liability.
    *   **Covered Entity Directory:** A view into the `CoveredEntityRegistry` listing verified healthcare providers.
    *   **EHRGate Visualizer:** A live monitor showing the 3-step PHI access check: (1) Patient Consent, (2) Active SmartBAA, and (3) Live Minimum AIS Score.
    *   **PHI Redaction & Data Minimization:** Visualizing the client-side `Redactor` pipeline. Shows how Protected Health Information is masked or tokenized *before* hitting the LLM, ensuring the "Minimum Necessary" HIPAA rule is strictly enforced.
    *   **HL7/FHIR Interoperability Logs:** Demonstrating how the agent communicates with standard EHR systems (Epic, Cerner) using secure, authenticated FHIR payloads.

### F. Xibalba Shield (Dedicated Agent Security Platform) (`/shield`)
*   **Purpose:** A robust Non-Human Identity (NHI) and security suite competing with platforms like Lakera, Operant AI, and Pillar Security.
*   **Implementation Details & Parity Features:**
    *   **The "9-Second Problem" Prevention:** Autonomous agents can delete databases in 9 seconds. Shield visualizes **Runtime Threat Detection**, showing the OPA policy gate intercepting prompt injections, memory poisoning, or unauthorized tool executions in real-time *before* they hit the target system.
    *   **NHI (Non-Human Identity) & Access Governance:** Treating agents as identities. UI for configuring "just-in-time" access and Principle of Least Privilege policies on specific MCP servers.
    *   **Shadow AI Discovery:** Automatically cataloging newly spawned agent processes and unregistered MCP servers connecting to the Oracle.
    *   **Forensics & Auditability (AI-BOM):** Generating downloadable NIST AI RMF compliance reports. Tracing the exact path of a rogue agent back to its cryptographic signature and slashing its $ITK stake via the `Slasher` primitive.
    *   **Red-Teaming Sandbox:** A dedicated area for security engineers to simulate adversarial attacks (jailbreaks) on the selected agent's prompt boundary.

### G. Financials ($ITK Wallet) (`/financials`)
*   **Purpose:** The DeFi interface for Agent Economics.
*   **Implementation Details:**
    *   **Portfolio:** Track $ITK available, staked on agents, or locked in escrow.
    *   **A2A Capital Allocation:** UI interfacing with the singleton `A2ACapitalPool.sol`.
    *   **Prediction Markets / Binary Options:** UI interfacing with `MarketFactory.sol` to deploy and bet on `IntegrityMarket` clones.

### H. Global Settings (`/settings`)
*   **Purpose:** Comprehensive user preference and workspace configuration.

---

## 5. Current vs. Planned Standards Matrix

| Standard / Feature | Component | Status | Description |
| :--- | :--- | :--- | :--- |
| **W3C DID v1.0** | Agent Identity | 🟢 Implemented | Base standard for `did:integrity:*` |
| **W3C VC Data Model** | Agent Reputation | 🟢 Implemented | Off-chain verifiable credentials for AIS evaluations |
| **ERC-20 ($ITK)** | Financials | 🟢 Implemented | Testnet utility token for staking and slashing |
| **ERC-721 (XNS)** | Registry | 🟢 Implemented | NFT-based human-readable agent domains (`.xibalba`) |
| **EIP-712** | Meta-Tx | 🟢 Implemented | Typed structured data hashing for gasless agent state updates |
| **EIP-1167** | Clones | 🟢 Implemented | `IntegrityMarket` and primitive clones per agent |
| **Noir / Barretenberg** | ZK Proving | 🟢 Implemented | Zero-knowledge circuits for confidential telemetry |
| **WebUSB / HID** | Hardware Wallet | 🟡 Planned | Direct integration with Ledger/Trezor for agent private key custody |
| **MCP Integration** | Telemetry | 🟢 Implemented | Standardized streaming of agent context to the Oracle |
| **Open Policy Agent**| Compliance | 🟢 Implemented | Rego-based pre-execution interceptors (Xibalba Shield) |
| **HL7/FHIR**| Interop | 🟡 Planned | EHR integration protocols for Integrity Health |

---

## 6. Project Architecture & Setup

```
integrity-mvp/
├── package.json
├── src/
│   ├── components/
│   │   ├── layout/          # Global Agent Selector, Sidebar, Topbar
│   │   ├── blocks/          # Notion-style expandable table blocks
│   │   ├── wallet/          # ITK Portfolio, A2ACapitalPool UI
│   │   ├── markets/         # IntegrityMarket Clone deployment & betting UI
│   │   ├── xns/             # Domain registry UI
│   │   ├── health/          # SmartBAA, Redactor, and EHRGate visualizations
│   │   ├── shield/          # Runtime threat detection, NHI Governance, Forensics
│   │   └── telemetry/       # Merkle Lens, Traces, Spans, and CoT visualizations
│   ├── pages/
│   │   ├── Landing/         # High-conversion business plan / value prop
│   │   ├── Dashboard/       # Customizable drag-and-drop workspace
│   │   ├── Identity/        # XNS and Agent Onboarding
│   │   ├── AIS/             # Deep dive into the Tri-Metric score
│   │   ├── Intelligence/    # Agent logs, MCP calls, Merkle Lens Explorer
│   │   ├── Health/          # Integrity Health (HIPAA / Healthcare Vertical)
│   │   ├── Shield/          # Xibalba Shield (Dedicated Agent Security)
│   │   ├── Financials/      # DeFi, Capital Pools, and Prediction Markets
│   │   └── Settings/        # Global typography, themes, layout
│   ├── context/
│   │   ├── AgentContext.tsx # Globally selected agent state
│   │   ├── ThemeContext.tsx # Hot-swappable UI themes
│   │   └── WalletContext.tsx# ITK integration state
│   └── App.tsx
└── README.md
```
