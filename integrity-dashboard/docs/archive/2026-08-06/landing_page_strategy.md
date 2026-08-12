# Integrity MVP — Landing Page Strategy & Structure

This document outlines the content strategy and UI flow for the `integrity-mvp` Landing Page. The page serves a dual purpose: it acts as a comprehensive **Business Plan** for investors, and it serves as an **MVP Walkthrough** that acquaints users with the core protocol features in logical order.

To prevent the design from becoming unbalanced or confusing, the page will strictly follow a linear narrative structure. It will utilize high-density information (paragraphs and lists) combined with novel UI cards to keep the reader engaged.

---

## 1. Global Navigation & Header
*   **Header Layout:** A sticky, translucent glassmorphism top navigation bar.
*   **Elements:** 
    *   Left: The **Xibalba Solutions Logo** alongside the "Integrity Protocol" logotype.
    *   Center: Quick jump anchors (Executive Summary, The Protocol, Market Verticals, FAQ).
    *   Right: Links to the GitHub Repository and Wiki, plus a primary "Launch MVP" button.

---

## 2. Hero Section: Executive Summary & Value Proposition
*   **Novel Value Proposition:** *"The Cryptographic Trust Layer for the Autonomous Economy. We don't just monitor AI—we mathematically bind it to liability."*
*   **Narrative:** The thesis of the company and the executive summary of the business plan. Introducing the Integrity Protocol as the missing infrastructure required for enterprise AI adoption.
*   **UI Elements:**
    *   Glowing neon typography against a deep slate background.
    *   A massive Xibalba Solutions logo integrated into a fluid, slow-moving Merkle tree or particle graph animation.
    *   A prominent "Launch MVP" call-to-action (CTA) button.

---

## 3. The Market Problem: Why This Exists
*   **Narrative:** AI agents are rapidly adopting autonomous capabilities (executing trades, accessing medical records, writing code), but they lack identity, liability, and governance. 
*   **Content (List format):**
    *   *The 9-Second Problem:* Agents can destroy infrastructure before human intervention.
    *   *Regulatory Void:* Current agents cannot legally sign BAAs or comply with HIPAA.
    *   *Black Box Telemetry:* Companies cannot prove *why* their agent took a specific action.
*   **UI Elements:** Red-tinted warning cards or a split-screen view contrasting "Legacy Web2 Security" vs. "Cryptographic Web3 Security."

---

## 4. Deep Dive: Agentic Integrity Score (AIS) & The Mathematics of Trust
*   **Narrative:** A comprehensive explanation of how we score agents objectively, replacing "vibes-based" evaluations with hard math and Zero-Knowledge proofs.
*   **Content & Math:** 
    *   Detailed explanations of the four pillars: Entropy, Grounding, Sacrifice, and Compliance.
    *   **LaTeX Rendered Equations:** The UI will feature beautifully rendered LaTeX blocks proving the geometric volume formula:
        $$ \text{AIS} = \left( S_{\text{entropy}}^{0.30} \cdot S_{\text{grounding}}^{0.30} \cdot S_{\text{sacrifice}}^{0.20} \cdot S_{\text{compliance}}^{0.20} \right) \cdot \text{ZK}_{\text{boost}} $$
    *   Explanation of the $\text{ZK}_{\text{boost}} = 1.15$ multiplier applied via Barretenberg proofs.
*   **UI Elements:** Dynamic, interactive mathematical graphs plotting AIS decay over time as hallucination rates (Grounding) drop.

---

## 5. MVP Walkthrough: The Core Protocol Features

*This section walks the user through the exact order of the MVP application pages, preparing them for the dashboard.*

### Step 1: Agent Identity & XNS (`/identity`)
*   **Business Plan Value:** Establishing verifiable Non-Human Identities (NHI).
*   **Content:** How agents generate DIDs and register on-chain. Explaining the Xibalba Name Service (XNS).

### Step 2: Observability & The Merkle Lens (`/intelligence`)
*   **Business Plan Value:** Unmatched forensic auditability for enterprise compliance (NIST AI RMF).
*   **UI Elements:** An interactive, embedded mini-version of the "Merkle Lens" where the user can hover over nodes to see SHA-256 derivations in real-time.

---

## 6. Business Proposal: Market Verticals
*   **Narrative:** How the core protocol adapts to specific, highly lucrative enterprise markets.

### Vertical A: Xibalba Shield (`/shield`)

This route is the frontend for the separate `xibalba-shield` endpoint-security product. Shield
is built on `INTEGRITY-LATEST` and exports its signed decisions into the protocol; the MVP
visualizes that evidence alongside the protocol's Oracle, BCC, identity, and reputation data.

*   **Market:** AI Security and Threat Detection (TDIR).
*   **Content:** Details on OPA policy interceptions, prompt injection blocking, and shadow AI discovery. Real-time agent security.

### Vertical B: Integrity Health (`/health`)
*   **Market:** Healthcare IT and HIPAA Compliance.
*   **Content:** The mechanics of the `SmartBAA`, the `EHRGate`, and the client-side PHI `Redactor`. A flowchart showing patient consent unlocking secure FHIR data.

### Vertical C: Decentralized Finance (`/financials`)
*   **Market:** DeFi and Agent Economics.
*   **Content:** The utility of the `$ITK` token. Staking for trust, slashing for hallucinations, and the `A2ACapitalPool` allocation markets.

---

## 7. The Competitive Moat (Standards Matrix)
*   **Narrative:** Why legacy Web2 companies cannot easily copy this. 
*   **Content:** A dense, highly technical table (mirroring Section 5 of our MVP plan) listing the exact Web3 and W3C standards we've implemented (DID v1.0, VC Data Model, ERC-721, EIP-712).
*   **UI Elements:** A sleek, block-based Notion-style table linking directly to the corresponding `docs/INTERFACE_CONTRACT.md` or repo files.

---

## 8. Detailed FAQ & Knowledge Base
*   **Narrative:** Preemptively answering investor and developer questions.
*   **Content:** An accordion-style UI covering topics like:
    *   *How does the Oracle derive signals without accessing PHI?*
    *   *What happens during a slashing event?*
    *   *How does the OPA middleware intercept intents in under 50ms?*
*   **Links:** Heavy cross-linking to specific `docs/wiki/` concept pages for deep technical validation.

---

## 9. Contact & Enterprise Onboarding
*   **UI Elements:** A high-quality, professional contact form for enterprise pilots, VCs, and partnership inquiries. Fields for Name, Organization, Use Case, and a direct message.

---

## 10. Global Footer & Final CTA
*   **Narrative:** A closing argument on the inevitability of autonomous agent economies and the necessity of a cryptographic trust layer.
*   **UI Elements:** 
    *   A massive, glowing "Launch MVP Dashboard" button.
    *   Footer links: GitHub Repo, Technical Wiki, Privacy Policy, Terms of Service, and Xibalba Solutions corporate links.
