//! Read-only on-chain client, via `alloy`, for the self-sovereign per-agent primitive
//! model described in `docs/INTERFACE_CONTRACT.md` §6.
//!
//! This is the piece that makes agent registration honest end-to-end: a client POSTing
//! to `/v1/agent/register` could claim any 7 addresses it likes, but `resolve_primitives`
//! independently asks `XibalbaAgentRegistry` (the on-chain source of truth, written
//! atomically and exclusively by `AgentPrimitivesFactory`, §6.3) what it actually
//! recorded for that DID, and the handler rejects any mismatch. Everything in this module
//! is a `view`/`pure` call — no wallet, no signing, no transaction submission — per the
//! interface contract's current phase ("the oracle only ever READS on-chain state").
//!
//! Interface fragments below are hand-transcribed from the real, compiled ABIs at
//! `contracts/out/{XibalbaAgentRegistry,ReputationRegistry,ComplianceGate}.sol/*.json`
//! (cross-checked field-for-field against `contracts/src/framework/XibalbaAgentRegistry.sol`,
//! `contracts/src/oracle/ReputationRegistry.sol`, `contracts/src/shield/ComplianceGate.sol`)
//! rather than generated from the JSON artifact at build time: `sol!`'s `#[sol(rpc)]` over
//! a hand-written interface produces the exact same ABI-encoding/decoding code as loading
//! the JSON would, without making this crate's build depend on `contracts/` having been
//! built first (a real constraint in this monorepo, where `contracts/out/` is `forge
//! build` output, not something `cargo build` can assume exists in every checkout/CI
//! environment). If the on-chain interfaces above ever change, this file and the
//! `contracts/` source must be updated together — there's no build-time check tying them
//! together, which is a documented gap (see `resolve_primitives`'s doc comment).

use std::path::Path;

use alloy::primitives::{keccak256, Address, B256, U256};
use alloy::providers::{DynProvider, Provider, ProviderBuilder};
use alloy::sol;
use serde::Deserialize;

sol! {
    #[sol(rpc)]
    interface IXibalbaAgentRegistry {
        struct PrimitiveSet {
            address sovereignAgent;
            address stateAnchor;
            address reputationRegistry;
            address slasher;
            address verifierRegistry;
            address complianceGate;
            address agentProfile;
        }

        struct AgentRecord {
            PrimitiveSet primitives;
            address controller;
            bytes32 domainId;
            uint256 registeredAt;
            bool exists;
        }

        function resolveDID(string calldata did) external view returns (AgentRecord memory record);
        function resolveAgent(address sovereignAgent) external view returns (AgentRecord memory record);
        function isRegisteredAgent(address sovereignAgent) external view returns (bool);
    }
}

sol! {
    #[sol(rpc)]
    interface IReputationRegistry {
        function effectiveScore(address agent) external view returns (uint256);
        function isZkBoosted(address agent) external view returns (bool);
    }
}

sol! {
    // Per-agent StateAnchor (contracts/src/oracle/StateAnchor.sol). Only the two
    // fields the registration memory gate needs: spec v0.3 §7.1 requires the oracle
    // to independently read `latestRoot` and reject a zero root at registration.
    // `latestEpoch` is read alongside it purely so the rejection message can say
    // whether the vault was never initialized at all.
    #[sol(rpc)]
    interface IStateAnchor {
        function latestRoot() external view returns (bytes32);
        function latestEpoch() external view returns (uint256);
    }
}

sol! {
    // Slasher's per-agent stake accounting is exposed via two public mappings
    // (contracts/src/oracle/Slasher.sol): total staked and the portion locked by
    // open disputes. Available = total - locked. Read-only, keyed on the staker
    // (the agent's SovereignAgent address).
    #[sol(rpc)]
    interface ISlasher {
        function stakeOf(address account) external view returns (uint256);
        function lockedStakeOf(address account) external view returns (uint256);
        function nextDisputeId() external view returns (uint256);
        function disputes(uint256 id) external view returns (
            address agent,
            uint256 amount,
            uint256 raisedAt,
            bool resolved,
            bool slashed,
            string reason
        );
    }
}

sol! {
    // A2ACapitalPool (contracts/src/markets/A2ACapitalPool.sol) escrows ITK
    // earmarked for an agent. There is no per-agent getter -- allocations are a
    // flat id->struct mapping -- so an agent's capital view is aggregated by
    // scanning allocations and filtering on the `agent` field. status: 0=Escrowed
    // 1=Released 2=ClawedBack 3=Breached. Read-only.
    #[sol(rpc)]
    interface IA2ACapitalPool {
        function nextAllocationId() external view returns (uint256);
        function allocations(uint256 id) external view returns (
            address allocator,
            address agent,
            uint256 amount,
            uint256 minAisToMaintain,
            uint8 status,
            uint256 createdAt
        );
    }
}

sol! {
    #[sol(rpc)]
    interface IComplianceGate {
        function vertical() external view returns (uint8);
        function isHealthcareCompliant(address coveredEntity) external view returns (bool);
    }
}

sol! {
    // Shield vertical. SmartBAAFactory (contracts/src/shield/SmartBAAFactory.sol) deploys
    // one SmartBAA escrow per (coveredEntity, businessAssociate) pair and emits BAACreated;
    // there is no reverse index from a business-associate agent to its BAAs, so the oracle
    // enumerates them from the BAACreated event log and reads each SmartBAA's live status.
    // SmartBAA.Status: 0=Proposed 1=Active 2=Disputed 3=Terminated.
    #[sol(rpc)]
    interface ISmartBAAFactory {
        function baaOf(address coveredEntity, address businessAssociate) external view returns (address);
        event BAACreated(address indexed coveredEntity, address indexed businessAssociate, address baa, bytes32 agreementHash);
    }
}

sol! {
    // XibalbaNameService (contracts/src/framework/XibalbaNameService.sol): a handle -> agent
    // name service. resolve() returns the SovereignAgent a handle points at (address(0) if
    // free); primaryHandle() returns an agent's chosen primary handle.
    #[sol(rpc)]
    interface IXibalbaNameService {
        function resolve(string calldata handle) external view returns (address sovereignAgent);
        function handleExists(string calldata handle) external view returns (bool);
        function primaryHandle(address sovereignAgent) external view returns (string memory);
    }
}

sol! {
    // IntegrityGovernance (contracts/src/oracle/IntegrityGovernance.sol): lock-to-vote,
    // timelocked governance. Enumerated by index: proposalCount() then getProposal(i) +
    // state(i) for i in 1..=count. ProposalState enum order matches the Solidity enum:
    // 0=Active 1=Defeated 2=Succeeded 3=Queued 4=Executed 5=Expired 6=Canceled.
    #[sol(rpc)]
    interface IIntegrityGovernance {
        struct Proposal {
            address proposer;
            address target;
            uint256 value;
            bytes callData;
            uint64 startTime;
            uint64 endTime;
            uint64 eta;
            uint256 forVotes;
            uint256 againstVotes;
            bool executed;
            bool canceled;
            string description;
        }
        function proposalCount() external view returns (uint256);
        function getProposal(uint256 id) external view returns (Proposal memory);
        function state(uint256 id) external view returns (uint8);
        function quorumVotes() external view returns (uint256);
        function votingPeriod() external view returns (uint256);
    }
}

sol! {
    #[sol(rpc)]
    interface ISmartBAA {
        function coveredEntity() external view returns (address);
        function businessAssociate() external view returns (address);
        function agreementHash() external view returns (bytes32);
        function requiredCollateral() external view returns (uint256);
        function status() external view returns (uint8);
    }
}

/// Hand-transcribed from `contracts/src/markets/MarketFactory.sol`. Note there is no
/// `allMarkets()` full-array getter: `address[] public allMarkets` only auto-generates
/// an indexed `allMarkets(uint256) returns (address)` getter, so enumerating every
/// market requires `allMarketsCount()` + a loop/batch over `allMarkets(i)` (see
/// `ChainClient::all_market_addresses`). `getMarketsByCreator` is the real full-array
/// getter for the by-creator case (the `marketsByCreator` mapping's auto-getter would
/// need an index too, same as `allMarkets`).
sol! {
    #[sol(rpc)]
    interface IMarketFactory {
        function allMarkets(uint256) external view returns (address);
        function allMarketsCount() external view returns (uint256);
        function getMarketsByCreator(address creator) external view returns (address[] memory);
    }
}

/// Hand-transcribed from `contracts/src/markets/IntegrityMarket.sol`.
sol! {
    #[sol(rpc)]
    interface IIntegrityMarket {
        struct Position {
            uint256 amount;
            uint8 outcomeIndex;
            bytes32 bccCommitmentHash;
            bool claimed;
        }

        function creator() external view returns (address);
        function question() external view returns (string memory);
        function outcomeCount() external view returns (uint8);
        function minAisToEnter() external view returns (uint256);
        function resolveDeadline() external view returns (uint256);
        function resolved() external view returns (bool);
        function winningOutcome() external view returns (uint8);
        function totalStaked() external view returns (uint256);
        function outcomeStaked(uint8) external view returns (uint256);
        function getPosition(address agent) external view returns (Position memory);
        function wasCorrect(address agent) external view returns (bool);
    }
}

/// Minimal ERC-20 read surface — just enough for `GET /v1/agent/{id}/wallet`'s real
/// `IntegrityToken.balanceOf` read.
sol! {
    #[sol(rpc)]
    interface IERC20Balance {
        function balanceOf(address account) external view returns (uint256);
    }
}

/// Mirrors `IXibalbaAgentRegistry.PrimitiveSet` as a plain Rust struct (rather than
/// exposing the `sol!`-generated type at this module's public boundary) so callers
/// elsewhere in the crate (handlers, db serialization) don't need to depend on alloy's
/// generated types directly — this is the crate-internal seam between "on-chain shape"
/// and "everything else".
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct PrimitiveSet {
    pub sovereign_agent: Address,
    pub state_anchor: Address,
    pub reputation_registry: Address,
    pub slasher: Address,
    pub verifier_registry: Address,
    pub compliance_gate: Address,
    pub agent_profile: Address,
}

impl From<IXibalbaAgentRegistry::PrimitiveSet> for PrimitiveSet {
    fn from(p: IXibalbaAgentRegistry::PrimitiveSet) -> Self {
        Self {
            sovereign_agent: p.sovereignAgent,
            state_anchor: p.stateAnchor,
            reputation_registry: p.reputationRegistry,
            slasher: p.slasher,
            verifier_registry: p.verifierRegistry,
            compliance_gate: p.complianceGate,
            agent_profile: p.agentProfile,
        }
    }
}

#[derive(Debug, Clone)]
pub struct AgentRecord {
    pub primitives: PrimitiveSet,
    pub controller: Address,
    pub domain_id: B256,
    pub registered_at: U256,
}

/// An agent's on-chain stake accounting from its `Slasher` clone (read via
/// `ChainClient::read_stake`). `available = total - locked`.
#[derive(Debug, Clone)]
pub struct StakeInfo {
    pub total: U256,
    pub locked: U256,
    pub available: U256,
    /// Count of this agent's currently-open (unresolved) disputes in its own Slasher
    /// clone. The dashboard sums this across the agent set it already iterates to get
    /// a real protocol-wide `active_disputes` with zero extra fan-out — see
    /// docs/design/dashboard-wiring.md; there is no singleton dispute index to read
    /// protocol-wide in one call.
    pub open_disputes: u64,
}

/// An agent's aggregated capital position in the A2ACapitalPool (read via
/// `ChainClient::read_credit`): totals by allocation status across every
/// allocation earmarked for that agent. `escrowed` is capital currently held for
/// the agent (its live available line); `released` has been disbursed.
#[derive(Debug, Clone, Default)]
pub struct CreditInfo {
    pub total_allocated: U256,
    pub escrowed: U256,
    pub released: U256,
    pub clawed_back: U256,
    pub breached: U256,
    pub allocation_count: u64,
}

/// One SmartBAA escrow's on-chain state, as read via `ChainClient::read_baas_for_agent`.
/// `status`: 0=Proposed 1=Active 2=Disputed 3=Terminated (SmartBAA.Status).
/// Plain-Rust mirror of one `IntegrityGovernance` proposal as read live by
/// `ChainClient::read_proposals`. `state` is the contract's derived `ProposalState` (0=Active
/// 1=Defeated 2=Succeeded 3=Queued 4=Executed 5=Expired 6=Canceled).
#[derive(Debug, Clone)]
pub struct ProposalInfo {
    pub id: u64,
    pub proposer: Address,
    pub target: Address,
    pub value: U256,
    pub start_time: u64,
    pub end_time: u64,
    pub eta: u64,
    pub for_votes: U256,
    pub against_votes: U256,
    pub state: u8,
    pub description: String,
}

#[derive(Debug, Clone)]
pub struct BaaInfo {
    pub address: Address,
    pub covered_entity: Address,
    pub business_associate: Address,
    pub agreement_hash: B256,
    pub required_collateral: U256,
    pub status: u8,
}

/// Plain-Rust mirror of an `IntegrityMarket` clone's on-chain view state, as read live
/// by `ChainClient::read_market` (§6.9). `outcome_staked[i]` is the pari-mutuel pool
/// for outcome `i` (cheap, bounded by `outcome_count` public-getter reads) — real
/// per-holder position enumeration would require indexing `PositionEntered` events,
/// which this pass does not build (see `entities/integrity-oracle.md`).
#[derive(Debug, Clone)]
pub struct MarketDetail {
    pub address: Address,
    pub creator: Address,
    pub question: String,
    pub outcome_count: u8,
    pub min_ais_to_enter: U256,
    pub resolve_deadline: U256,
    pub resolved: bool,
    pub winning_outcome: u8,
    pub total_staked: U256,
    pub outcome_staked: Vec<U256>,
}

/// Plain-Rust mirror of `IIntegrityMarket::Position`.
#[derive(Debug, Clone, Copy)]
pub struct MarketPosition {
    pub amount: U256,
    pub outcome_index: u8,
    pub bcc_commitment_hash: B256,
    pub claimed: bool,
}

impl From<IIntegrityMarket::Position> for MarketPosition {
    fn from(p: IIntegrityMarket::Position) -> Self {
        Self {
            amount: p.amount,
            outcome_index: p.outcomeIndex,
            bcc_commitment_hash: p.bccCommitmentHash,
            claimed: p.claimed,
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum ChainError {
    #[error("failed to read/parse deployments file {path}: {source}")]
    DeploymentsFile {
        path: String,
        source: anyhow::Error,
    },
    #[error("no agent registered for DID {0}")]
    UnknownDid(String),
    #[error("no agent registered for SovereignAgent address {0}")]
    UnknownAgent(Address),
    #[error("required singleton '{0}' is missing from the deployments file (not deployed on this network)")]
    MissingSingleton(&'static str),
    #[error("on-chain call failed: {0}")]
    Rpc(#[from] alloy::contract::Error),
    #[error("RPC transport error: {0}")]
    Transport(#[from] alloy::transports::RpcError<alloy::transports::TransportErrorKind>),
}

/// Deserializes exactly the subset of `deployments.local.json` (§6.6) this client needs:
/// `singletons.XibalbaAgentRegistry`. The full file has more sections (`cloneTemplates`,
/// `protocolAddresses`, `domains`) that this phase's read-only client has no use for, so
/// they're intentionally not modeled here — `serde(deny_unknown_fields)` is deliberately
/// NOT set, so this stays forward-compatible with fields other packages add later.
#[derive(Debug, Deserialize)]
struct DeploymentsFile {
    singletons: Singletons,
}

#[derive(Debug, Deserialize)]
struct Singletons {
    #[serde(rename = "XibalbaAgentRegistry")]
    xibalba_agent_registry: Address,
    /// `Option` (not required): genesis-only deployments files (e.g. produced by a
    /// `Deploy.s.sol` run that predates the market layer) may not have this key yet —
    /// see `MarketFactory`/`A2ACapitalPool`'s addition via the incremental
    /// `DeployMarkets.s.sol` (§6.6/§6.9). Handlers that need it report a clean
    /// "market layer not deployed" error rather than this client failing to even
    /// connect.
    #[serde(rename = "MarketFactory", default)]
    market_factory: Option<Address>,
    #[serde(rename = "IntegrityToken", default)]
    integrity_token: Option<Address>,
    /// `Option` for the same incremental-deploy reason as `MarketFactory` — the
    /// A2ACapitalPool singleton is added by `DeployMarkets.s.sol`; the credit
    /// endpoint reports "capital pool not deployed" cleanly if it's absent.
    #[serde(rename = "A2ACapitalPool", default)]
    a2a_capital_pool: Option<Address>,
    /// `Option` — the Shield vertical's SmartBAAFactory. Absent on non-Shield or
    /// genesis-only deployments; shield read endpoints report it cleanly if missing.
    #[serde(rename = "SmartBAAFactory", default)]
    smart_baa_factory: Option<Address>,
    /// `Option` — XibalbaNameService (XNS). Absent until deployed; resolve endpoints report
    /// it cleanly if missing.
    #[serde(rename = "XibalbaNameService", default)]
    xibalba_name_service: Option<Address>,
    /// `Option` — IntegrityGovernance. Absent until deployed; the governance read endpoint
    /// reports it cleanly (503) if missing.
    #[serde(rename = "IntegrityGovernance", default)]
    integrity_governance: Option<Address>,
}

/// Read-only on-chain client. Holds a connected `alloy` provider and the resolved
/// `XibalbaAgentRegistry` address; cheap to clone (provider is internally `Arc`-backed)
/// so one instance is constructed at startup and shared across the Axum app.
///
/// The provider is stored as alloy's `DynProvider` — a concrete, `Sized`, type-erased
/// provider — rather than an `Arc<dyn Provider>` trait object: `sol!`'s `#[sol(rpc)]`
/// generated contract bindings require a `Sized` provider type (`ContractInstance::new`
/// bounds `P: Provider`, which a `?Sized` trait object doesn't satisfy), and
/// `DynProvider` is alloy's purpose-built answer for "erase the concrete provider type
/// but stay usable with the generated bindings". It's `Clone` and internally `Arc`-backed,
/// so cloning stays cheap.
#[derive(Clone)]
pub struct ChainClient {
    provider: DynProvider,
    registry_address: Address,
    market_factory_address: Option<Address>,
    integrity_token_address: Option<Address>,
    a2a_capital_pool_address: Option<Address>,
    smart_baa_factory_address: Option<Address>,
    xibalba_name_service_address: Option<Address>,
    integrity_governance_address: Option<Address>,
}

/// True iff a failed contract `.call()` reverted with `UnknownDID()`
/// (selector `0x4c2a24b3`, `cast sig "UnknownDID()"`) rather than some other failure
/// (RPC unreachable, malformed response, an unrelated revert). Extracted as a pure
/// function, separate from `resolve_primitives_by_did`'s tracing call, specifically so
/// this classification is unit-testable without a live provider — see the test module
/// at the end of this file.
fn is_unknown_did_revert(err: &alloy::contract::Error) -> bool {
    const UNKNOWN_DID_SELECTOR: [u8; 4] = [0x4c, 0x2a, 0x24, 0xb3];
    err.as_revert_data()
        .is_some_and(|data| data.get(..4) == Some(UNKNOWN_DID_SELECTOR.as_slice()))
}

impl ChainClient {
    /// Connects to `rpc_url` and reads `deployments_file` for the registry address.
    /// Per the interface contract (§6.6), only `singletons`/`cloneTemplates` addresses
    /// ever come from this static file — per-agent primitive addresses are always
    /// resolved live via `resolve_primitives`, never read from any file.
    pub async fn connect(rpc_url: &str, deployments_file: &Path) -> Result<Self, ChainError> {
        let raw = std::fs::read_to_string(deployments_file).map_err(|e| ChainError::DeploymentsFile {
            path: deployments_file.display().to_string(),
            source: e.into(),
        })?;
        let parsed: DeploymentsFile = serde_json::from_str(&raw).map_err(|e| ChainError::DeploymentsFile {
            path: deployments_file.display().to_string(),
            source: e.into(),
        })?;

        let url = rpc_url.parse().map_err(|e: url::ParseError| ChainError::DeploymentsFile {
            path: rpc_url.to_string(),
            source: anyhow::anyhow!(e),
        })?;
        let provider = ProviderBuilder::new().connect_http(url);

        Ok(Self {
            provider: provider.erased(),
            registry_address: parsed.singletons.xibalba_agent_registry,
            market_factory_address: parsed.singletons.market_factory,
            integrity_token_address: parsed.singletons.integrity_token,
            a2a_capital_pool_address: parsed.singletons.a2a_capital_pool,
            smart_baa_factory_address: parsed.singletons.smart_baa_factory,
            xibalba_name_service_address: parsed.singletons.xibalba_name_service,
            integrity_governance_address: parsed.singletons.integrity_governance,
        })
    }

    /// Constructs a client directly from an already-known registry address, bypassing the
    /// deployments file. Used by tests that deploy their own registry against a local
    /// anvil instance and don't want to round-trip through a JSON file on disk.
    pub fn with_registry_address(provider: impl Provider + 'static, registry_address: Address) -> Self {
        Self {
            provider: provider.erased(),
            registry_address,
            market_factory_address: None,
            integrity_token_address: None,
            a2a_capital_pool_address: None,
            smart_baa_factory_address: None,
            xibalba_name_service_address: None,
            integrity_governance_address: None,
        }
    }

    /// Same as [`Self::with_registry_address`], but also wires the market/token
    /// singletons — used by tests that need `GET /v1/markets`-family endpoints against
    /// a locally-deployed `MarketFactory`/`IntegrityToken`.
    pub fn with_market_layer(
        provider: impl Provider + 'static,
        registry_address: Address,
        market_factory_address: Address,
        integrity_token_address: Address,
    ) -> Self {
        Self {
            provider: provider.erased(),
            registry_address,
            market_factory_address: Some(market_factory_address),
            integrity_token_address: Some(integrity_token_address),
            a2a_capital_pool_address: None,
            smart_baa_factory_address: None,
            xibalba_name_service_address: None,
            integrity_governance_address: None,
        }
    }

    fn registry(&self) -> IXibalbaAgentRegistry::IXibalbaAgentRegistryInstance<DynProvider> {
        IXibalbaAgentRegistry::new(self.registry_address, self.provider.clone())
    }

    /// Resolves an agent's full 7-address `PrimitiveSet` by DID, straight from
    /// `XibalbaAgentRegistry.resolveDID` (§6.1). This is the authoritative on-chain read
    /// that `POST /v1/agent/register` cross-checks a client's claimed addresses against —
    /// see this module's top-level doc comment for why that check matters.
    pub async fn resolve_primitives_by_did(&self, did: &str) -> Result<AgentRecord, ChainError> {
        let record = self
            .registry()
            .resolveDID(did.to_string())
            .call()
            .await
            .map_err(|err| {
                // `UnknownDID()` (selector 0x4c2a24b3, `cast sig "UnknownDID()"`) is the
                // registry's ordinary response to a DID that was never registered on
                // THIS chain -- e.g. an anvil-era row queried against a Sepolia-configured
                // oracle (PRODUCTION_GAPS.md §24, audit E11/E12). That is not an infra
                // problem, so it does not belong at ERROR: hundreds of routine "not
                // found" lookups logging at ERROR is exactly what made a fully healthy
                // service read as a total outage during the 2026-07-31 incident -- the
                // polling itself, not any real fault, is what filled the log. Anything
                // else here (RPC unreachable, malformed response, an unexpected revert)
                // still logs at ERROR, because that IS actionable.
                if is_unknown_did_revert(&err) {
                    tracing::warn!("resolveDID: DID {} not registered on this chain", did);
                } else {
                    tracing::error!("resolveDID contract call failed for DID {}: {:?}", did, err);
                }
                ChainError::UnknownDid(did.to_string())
            })?;
        if !record.exists {
            return Err(ChainError::UnknownDid(did.to_string()));
        }
        Ok(AgentRecord {
            primitives: record.primitives.into(),
            controller: record.controller,
            domain_id: record.domainId,
            registered_at: record.registeredAt,
        })
    }

    /// Same resolution, keyed by the agent's `SovereignAgent` contract address instead of
    /// its DID — used by `GET /v1/agent/{id}/compliance` and similar reads where the
    /// caller already has the canonical on-chain address (e.g. from a cached
    /// `agent_primitives` row) rather than the DID string.
    pub async fn resolve_primitives_by_address(&self, sovereign_agent: Address) -> Result<AgentRecord, ChainError> {
        let record = self
            .registry()
            .resolveAgent(sovereign_agent)
            .call()
            .await
            .map_err(|_| ChainError::UnknownAgent(sovereign_agent))?;
        if !record.exists {
            return Err(ChainError::UnknownAgent(sovereign_agent));
        }
        Ok(AgentRecord {
            primitives: record.primitives.into(),
            controller: record.controller,
            domain_id: record.domainId,
            registered_at: record.registeredAt,
        })
    }

    /// `keccak256(bytes(did))` — mirrors `XibalbaAgentRegistry.didHash` (a `pure`
    /// function we can just as cheaply compute client-side rather than round-tripping an
    /// RPC call for it).
    pub fn did_hash(did: &str) -> B256 {
        keccak256(did.as_bytes())
    }

    /// Reads `ReputationRegistry.effectiveScore` for a specific agent's own
    /// ReputationRegistry clone address (resolved via `resolve_primitives_*` first — this
    /// client never guesses which clone belongs to which agent).
    pub async fn effective_score(&self, reputation_registry: Address, agent: Address) -> Result<U256, ChainError> {
        let contract = IReputationRegistry::new(reputation_registry, self.provider.clone());
        Ok(contract.effectiveScore(agent).call().await?)
    }

    pub async fn is_zk_boosted(&self, reputation_registry: Address, agent: Address) -> Result<bool, ChainError> {
        let contract = IReputationRegistry::new(reputation_registry, self.provider.clone());
        Ok(contract.isZkBoosted(agent).call().await?)
    }

    /// Reads an agent's real stake accounting from its own `Slasher` clone:
    /// total staked and the portion locked by open disputes (available = total
    /// - locked). `account` is the staker — the agent's SovereignAgent address.
    /// Two `view` calls, no state change (this client only ever reads).
    pub async fn read_stake(&self, slasher: Address, account: Address) -> Result<StakeInfo, ChainError> {
        let contract = ISlasher::new(slasher, self.provider.clone());
        let total = contract.stakeOf(account).call().await?;
        let locked = contract.lockedStakeOf(account).call().await?;
        // Open-dispute count: scan this clone's disputes and count the agent's
        // unresolved ones. The Slasher is a per-agent clone, so `nextDisputeId` is
        // bounded by just this agent's dispute history (cheap); the `d.agent ==
        // account` filter is belt-and-suspenders against a shared/misconfigured clone.
        let next_dispute_id = contract.nextDisputeId().call().await?.to::<u64>();
        let mut open_disputes = 0u64;
        for i in 0..next_dispute_id {
            let d = contract.disputes(U256::from(i)).call().await?;
            if !d.resolved && d.agent == account {
                open_disputes += 1;
            }
        }
        Ok(StakeInfo {
            total,
            locked,
            available: total.saturating_sub(locked),
            open_disputes,
        })
    }

    /// The A2ACapitalPool singleton address, if the market/capital layer is
    /// deployed (see `DeployMarkets.s.sol`). `None` -> handler reports it cleanly.
    pub fn a2a_capital_pool(&self) -> Option<Address> {
        self.a2a_capital_pool_address
    }

    /// Aggregates an agent's real capital position across every allocation in the
    /// pool earmarked for `agent` (its SovereignAgent address). Scans allocations
    /// 0..nextAllocationId -- O(N) view calls, acceptable at current scale; a
    /// per-agent index would replace this if the pool grows large.
    pub async fn read_credit(&self, pool: Address, agent: Address) -> Result<CreditInfo, ChainError> {
        self.scan_allocations(pool, Some(agent)).await
    }

    /// Protocol-wide capital totals: the same allocation scan as `read_credit`, but
    /// unfiltered (every allocation, all agents). Backs `GET /v1/stats`
    /// (`total_loans_volume` = released, the escrowed slice of `tvl`) in a single pass
    /// over the singleton pool — not an N-agent fan-out.
    pub async fn read_pool_totals(&self, pool: Address) -> Result<CreditInfo, ChainError> {
        self.scan_allocations(pool, None).await
    }

    /// Shared allocation scan. `agent = Some(a)` aggregates only `a`'s allocations
    /// (per-agent credit view); `agent = None` aggregates every allocation
    /// (protocol-wide totals). O(nextAllocationId) view calls either way.
    async fn scan_allocations(&self, pool: Address, agent: Option<Address>) -> Result<CreditInfo, ChainError> {
        let contract = IA2ACapitalPool::new(pool, self.provider.clone());
        let count = contract.nextAllocationId().call().await?;
        let n = count.to::<u64>();
        let mut info = CreditInfo::default();
        for i in 0..n {
            let a = contract.allocations(U256::from(i)).call().await?;
            if let Some(target) = agent {
                if a.agent != target {
                    continue;
                }
            }
            info.allocation_count += 1;
            info.total_allocated += a.amount;
            match a.status {
                0 => info.escrowed += a.amount,
                1 => info.released += a.amount,
                2 => info.clawed_back += a.amount,
                3 => info.breached += a.amount,
                _ => {}
            }
        }
        Ok(info)
    }

    /// 0 = `Vertical.None`, 1 = `Vertical.Healthcare` (see `ComplianceGate.sol`'s enum —
    /// deliberately read back as a raw `u8` here rather than a Rust enum, since this
    /// client has no business asserting which vertical values are valid; that's the
    /// contract's job, and a future added vertical shouldn't require an oracle redeploy
    /// just to stop erroring on an unrecognized discriminant).
    pub async fn compliance_vertical(&self, compliance_gate: Address) -> Result<u8, ChainError> {
        let contract = IComplianceGate::new(compliance_gate, self.provider.clone());
        Ok(contract.vertical().call().await?)
    }

    pub async fn is_healthcare_compliant(&self, compliance_gate: Address, covered_entity: Address) -> Result<bool, ChainError> {
        let contract = IComplianceGate::new(compliance_gate, self.provider.clone());
        Ok(contract.isHealthcareCompliant(covered_entity).call().await?)
    }

    /// The Shield SmartBAAFactory singleton, if deployed. `None` -> handler reports it cleanly.
    pub fn smart_baa_factory(&self) -> Option<Address> {
        self.smart_baa_factory_address
    }

    /// The XibalbaNameService (XNS) singleton, if deployed.
    pub fn xibalba_name_service(&self) -> Option<Address> {
        self.xibalba_name_service_address
    }

    /// Resolve an XNS handle to the SovereignAgent it points at (address(0) if unregistered).
    /// `resolve()` reverts on an unclaimed handle, so gate on `handleExists` first and return
    /// the zero address for "not registered" — a resolvable, non-error outcome for callers.
    pub async fn resolve_handle(&self, xns: Address, handle: &str) -> Result<Address, ChainError> {
        let c = IXibalbaNameService::new(xns, self.provider.clone());
        if !c.handleExists(handle.to_string()).call().await? {
            return Ok(Address::ZERO);
        }
        Ok(c.resolve(handle.to_string()).call().await?)
    }

    /// The agent's own memory state: `(latestRoot, latestEpoch)` from its `StateAnchor`.
    ///
    /// Spec v0.3 §4.1/§7.1: an agent's Trust Vault commitment is its persistent-memory
    /// primitive, and registration requires `latestRoot != bytes32(0)`. Read directly from
    /// chain, never from the client's claim or this oracle's DB — the same
    /// independent-read posture as `resolve_primitives_by_did`, and for the same reason:
    /// the chain is the source of truth, so the check has to ask the chain.
    pub async fn memory_state(&self, state_anchor: Address) -> Result<(B256, U256), ChainError> {
        let c = IStateAnchor::new(state_anchor, self.provider.clone());
        let root = c.latestRoot().call().await?;
        let epoch = c.latestEpoch().call().await?;
        Ok((root, epoch))
    }

    /// The agent's chosen primary handle ("" if none).
    pub async fn primary_handle(&self, xns: Address, agent: Address) -> Result<String, ChainError> {
        let c = IXibalbaNameService::new(xns, self.provider.clone());
        Ok(c.primaryHandle(agent).call().await?)
    }

    /// The IntegrityGovernance singleton, if deployed.
    pub fn integrity_governance(&self) -> Option<Address> {
        self.integrity_governance_address
    }

    /// Enumerates every governance proposal by index (`proposalCount()` then `getProposal(i)` +
    /// `state(i)` for i in 1..=count). Proposal ids are 1-based (see `propose`'s `++proposalCount`).
    /// Newest-first. A per-proposal read error is skipped rather than failing the whole list.
    pub async fn read_proposals(&self, gov: Address) -> Result<Vec<ProposalInfo>, ChainError> {
        let c = IIntegrityGovernance::new(gov, self.provider.clone());
        let count: U256 = c.proposalCount().call().await?;
        let count = count.to::<u64>();
        let mut out = Vec::new();
        for id in (1..=count).rev() {
            let p = match c.getProposal(U256::from(id)).call().await {
                Ok(p) => p,
                Err(_) => continue,
            };
            let state = c.state(U256::from(id)).call().await.unwrap_or(0u8);
            out.push(ProposalInfo {
                id,
                proposer: p.proposer,
                target: p.target,
                value: p.value,
                start_time: p.startTime,
                end_time: p.endTime,
                eta: p.eta,
                for_votes: p.forVotes,
                against_votes: p.againstVotes,
                state,
                description: p.description,
            });
        }
        Ok(out)
    }

    /// Enumerates every SmartBAA where `business_associate` (an agent's SovereignAgent) is
    /// the BA, by scanning `SmartBAAFactory.BAACreated` logs and reading each escrow's live
    /// status. There is no reverse index on-chain, so the event log is the only enumeration
    /// path. Scans from genesis (`from_block(0)`); acceptable at testnet BAA volume — a very
    /// large history would want a bounded from-block or a cached index.
    pub async fn read_baas_for_agent(&self, factory: Address, business_associate: Address) -> Result<Vec<BaaInfo>, ChainError> {
        use alloy::rpc::types::Filter;
        use alloy::sol_types::SolEvent;

        let filter = Filter::new()
            .address(factory)
            .event_signature(ISmartBAAFactory::BAACreated::SIGNATURE_HASH)
            .from_block(0u64);
        let logs = self.provider.get_logs(&filter).await?;

        let mut out = Vec::new();
        for log in logs {
            let Ok(decoded) = ISmartBAAFactory::BAACreated::decode_log(&log.inner) else { continue };
            if decoded.data.businessAssociate != business_associate {
                continue;
            }
            let baa = ISmartBAA::new(decoded.data.baa, self.provider.clone());
            let status = baa.status().call().await?;
            let required_collateral = baa.requiredCollateral().call().await?;
            out.push(BaaInfo {
                address: decoded.data.baa,
                covered_entity: decoded.data.coveredEntity,
                business_associate: decoded.data.businessAssociate,
                agreement_hash: decoded.data.agreementHash,
                required_collateral,
                status,
            });
        }
        Ok(out)
    }

    pub fn market_factory_address(&self) -> Option<Address> {
        self.market_factory_address
    }

    fn market_factory(&self) -> Result<IMarketFactory::IMarketFactoryInstance<DynProvider>, ChainError> {
        let addr = self.market_factory_address.ok_or(ChainError::MissingSingleton("MarketFactory"))?;
        Ok(IMarketFactory::new(addr, self.provider.clone()))
    }

    /// Full membership of `MarketFactory.allMarkets` — `allMarketsCount()` first, then
    /// every `allMarkets(i)` read concurrently (`futures::future::join_all`), since
    /// there's no single-call full-array getter (see this module's `IMarketFactory` doc
    /// comment). This is the source of truth GET /v1/markets re-enumerates against on a
    /// cache-staleness miss, so a brand-new market (created after the last sync) is
    /// actually discovered, not just existing cached rows refreshed in place.
    pub async fn all_market_addresses(&self) -> Result<Vec<Address>, ChainError> {
        let factory = self.market_factory()?;
        let count: U256 = factory.allMarketsCount().call().await?;
        let count: u64 = count.try_into().unwrap_or(u64::MAX);

        let reads = (0..count).map(|i| {
            let factory = &factory;
            async move { factory.allMarkets(U256::from(i)).call().await }
        });
        let results = futures::future::join_all(reads).await;

        let mut addresses = Vec::with_capacity(results.len());
        for r in results {
            addresses.push(r?);
        }
        Ok(addresses)
    }

    pub async fn markets_by_creator(&self, creator: Address) -> Result<Vec<Address>, ChainError> {
        let factory = self.market_factory()?;
        Ok(factory.getMarketsByCreator(creator).call().await?)
    }

    /// Reads one `IntegrityMarket` clone's full view state (question, outcome
    /// structure, resolution status, and the per-outcome pari-mutuel pool — see
    /// `MarketDetail`'s doc comment on what's cheap vs. what needs event indexing).
    /// Every field read concurrently rather than sequentially awaited one-by-one.
    pub async fn read_market(&self, market: Address) -> Result<MarketDetail, ChainError> {
        let contract = IIntegrityMarket::new(market, self.provider.clone());

        // Each `.call()` builder must be bound to a local before it's awaited
        // inline in the macro below — alloy's `SolCallBuilder::call()` future
        // borrows from the builder, so passing `contract.field().call()`
        // directly as a macro argument makes the builder a dropped-too-early
        // temporary (E0716). Naming each one keeps it alive for the join.
        let creator_call = contract.creator();
        let question_call = contract.question();
        let outcome_count_call = contract.outcomeCount();
        let min_ais_to_enter_call = contract.minAisToEnter();
        let resolve_deadline_call = contract.resolveDeadline();
        let resolved_call = contract.resolved();
        let winning_outcome_call = contract.winningOutcome();
        let total_staked_call = contract.totalStaked();

        let (creator, question, outcome_count, min_ais_to_enter, resolve_deadline, resolved, winning_outcome, total_staked) = tokio::try_join!(
            creator_call.call(),
            question_call.call(),
            outcome_count_call.call(),
            min_ais_to_enter_call.call(),
            resolve_deadline_call.call(),
            resolved_call.call(),
            winning_outcome_call.call(),
            total_staked_call.call(),
        )?;

        let outcome_staked_reads = (0..outcome_count).map(|i| {
            let contract = contract.clone();
            async move { contract.outcomeStaked(i).call().await }
        });
        let outcome_staked_results = futures::future::join_all(outcome_staked_reads).await;
        let mut outcome_staked = Vec::with_capacity(outcome_staked_results.len());
        for r in outcome_staked_results {
            outcome_staked.push(r?);
        }

        Ok(MarketDetail {
            address: market,
            creator,
            question,
            outcome_count,
            min_ais_to_enter,
            resolve_deadline,
            resolved,
            winning_outcome,
            total_staked,
            outcome_staked,
        })
    }

    /// Batch version of [`Self::read_market`] for `GET /v1/markets` — concurrent, not a
    /// serial loop (per the task brief: "there could be dozens"). A market whose read
    /// fails (e.g. transient RPC hiccup) is logged and skipped rather than failing the
    /// whole listing.
    pub async fn read_markets(&self, addresses: &[Address]) -> Vec<MarketDetail> {
        let reads = addresses.iter().map(|&addr| async move {
            match self.read_market(addr).await {
                Ok(detail) => Some(detail),
                Err(e) => {
                    tracing::warn!(market = %addr, error = %e, "skipping market in batch read");
                    None
                }
            }
        });
        futures::future::join_all(reads).await.into_iter().flatten().collect()
    }

    pub async fn get_position(&self, market: Address, agent: Address) -> Result<MarketPosition, ChainError> {
        let contract = IIntegrityMarket::new(market, self.provider.clone());
        Ok(contract.getPosition(agent).call().await?.into())
    }

    /// Real `IntegrityToken.balanceOf` read for `GET /v1/agent/{id}/wallet`.
    pub async fn itk_balance_of(&self, account: Address) -> Result<U256, ChainError> {
        let addr = self.integrity_token_address.ok_or(ChainError::MissingSingleton("IntegrityToken"))?;
        let contract = IERC20Balance::new(addr, self.provider.clone());
        Ok(contract.balanceOf(account).call().await?)
    }
}

#[cfg(test)]
mod resolve_did_error_classification_tests {
    //! Unit tests for `is_unknown_did_revert`, the discriminator that decides whether a
    //! failed `resolveDID` call logs at `warn` (an ordinary "not registered on this
    //! chain" outcome) or `error` (something actually wrong). Constructed directly from
    //! JSON-RPC error payloads rather than through a live provider, matching the shape
    //! observed in real production logs (audit E12,
    //! docs/design/e2e-audit-2026-07-31.md): `ErrorResp(ErrorPayload { code: 3, message:
    //! "execution reverted", data: Some(RawValue("0x4c2a24b3")) })`.

    use super::is_unknown_did_revert;
    use alloy::transports::TransportError;
    use alloy_json_rpc::ErrorPayload;

    fn contract_error_from_revert_data_hex(hex: &str) -> alloy::contract::Error {
        let json = format!(r#"{{"code":3,"message":"execution reverted","data":"{hex}"}}"#);
        let payload: ErrorPayload = serde_json::from_str(&json).expect("valid ErrorPayload JSON");
        TransportError::ErrorResp(payload).into()
    }

    #[test]
    fn recognizes_the_real_unknown_did_selector() {
        // 0x4c2a24b3 == cast sig "UnknownDID()", confirmed against the live registry
        // this session (docs/design/e2e-audit-2026-07-31.md).
        let err = contract_error_from_revert_data_hex("0x4c2a24b3");
        assert!(is_unknown_did_revert(&err));
    }

    #[test]
    fn does_not_match_a_different_four_byte_selector() {
        // AlreadyRegistered() on the same registry -- a real selector, just not this one.
        let err = contract_error_from_revert_data_hex("0x2ca69173");
        assert!(!is_unknown_did_revert(&err));
    }

    #[test]
    fn does_not_match_the_right_selector_with_extra_trailing_bytes_absent_wrong_prefix() {
        // A selector that merely CONTAINS the same bytes elsewhere must not match --
        // only a match at the start (the actual selector position) counts.
        let err = contract_error_from_revert_data_hex("0xdeadbeef4c2a24b3");
        assert!(!is_unknown_did_revert(&err));
    }

    #[test]
    fn does_not_match_when_there_is_no_revert_data_at_all() {
        let json = r#"{"code":-32000,"message":"connection refused"}"#;
        let payload: ErrorPayload = serde_json::from_str(json).unwrap();
        let err: alloy::contract::Error = TransportError::ErrorResp(payload).into();
        assert!(!is_unknown_did_revert(&err));
    }

    #[test]
    fn does_not_match_a_non_revert_transport_error() {
        // A message that doesn't even mention "revert" -- ErrorPayload::as_revert_data
        // itself refuses to interpret unrelated errors (e.g. rate limiting) as revert
        // data, and this discriminator must not accidentally bypass that.
        let err = contract_error_from_revert_data_hex_with_message(
            "rate limited, try again in 4ms",
            "0x4c2a24b3",
        );
        assert!(!is_unknown_did_revert(&err));
    }

    fn contract_error_from_revert_data_hex_with_message(message: &str, hex: &str) -> alloy::contract::Error {
        let json = format!(r#"{{"code":-32005,"message":"{message}","data":"{hex}"}}"#);
        let payload: ErrorPayload = serde_json::from_str(&json).expect("valid ErrorPayload JSON");
        TransportError::ErrorResp(payload).into()
    }
}
