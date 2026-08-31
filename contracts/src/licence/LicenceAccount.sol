// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import {ECDSA} from "@openzeppelin/contracts/utils/cryptography/ECDSA.sol";
import {EIP712} from "@openzeppelin/contracts/utils/cryptography/EIP712.sol";
import {Nonces} from "@openzeppelin/contracts/utils/Nonces.sol";
import {IAccount, IEntryPoint, PackedUserOperation} from "@openzeppelin/contracts/interfaces/draft-IERC4337.sol";
import {ERC4337Utils} from "@openzeppelin/contracts/account/utils/draft-ERC4337Utils.sol";
import {IERC6551Account} from "./IERC6551.sol";
import {ILicenceHook} from "./ILicenceHook.sol";
import {ILicenceTermsHook, LicenceTermsContext} from "./ILicenceTermsHook.sol";
import {AdapterRegistry} from "../registry/AdapterRegistry.sol";

/// @title LicenceAccount
/// @notice Phase II tracer-bullet slice
/// (`docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`): an ERC-6551
/// token-bound account representing intellectual property as a live, metered asset
/// (whitepaper §5.1-5.4). The default account enforces THREE licence terms from Table 2 -- volume cap
/// (monotone depletion, eq 13), royalty (value conservation, eq 12), and expiry (a plain block-
/// timestamp bound) -- plus the transfer-drain guard (eq 17). Additive ATCP/IP EIP-712 intents,
/// account-side ERC-4337 validation, an optional licence hook, and the Phase III adapter-registry
/// hook are implemented as separate layers. `LicenceTermsPolicy` adds the other six Table 2 terms
/// through the typed hook path; unconfigured accounts retain the narrow default behavior.
/// State channels, live sponsorship, and production governance remain deferred.
///
/// @dev **Deliberately ONE implementation contract PER LICENCE, not a shared implementation
/// reused across many licences via bytecode-introspected context-reading** (the more common
/// real-world ERC-6551 pattern, used for gas efficiency at scale). This slice's licence terms
/// (volume cap, royalty rate, expiry window, and which NFT controls it) are all `immutable`,
/// baked into THIS contract's own bytecode at construction -- correct and simple for proving the
/// concept with one reference licence, not gas-optimized for deploying thousands. A real
/// implementation-sharing design is separate, later scope, matching Phase I's own "prove it
/// narrow first, generalize later" precedent.
///
/// **Value conservation (royalty) does NOT use a separate accounting variable.** Per whitepaper
/// eq (16), $b_I$ (accrued royalties) IS the account's own native-token balance -- `consume()`
/// deposits `msg.value` directly into `address(this).balance`, and `execute()`'s withdrawal path
/// (via a native-value `call`) is what the transfer-drain guard actually gates. This is a hard
/// invariant, same category as Phase I's own declared-token conservation (`IntegrityKernel`'s
/// `trackedToken`) -- never cached, checked live.
///
/// **`operation` in `execute()` supports ONLY `0` (CALL)** -- DELEGATECALL/CREATE/CREATE2 (values
/// 1-3 in the ERC-6551 convention this interface borrows from Safe-style multisig calls) are
/// rejected. Matches `IntegrityAccount`'s own single-execution-mode discipline for the identical
/// reason: a narrower attack surface is easier to reason about completely.
///
/// **Concrete guarantees this slice proves** (77 Foundry tests --
/// `test/licence/LicenceAccount.t.sol`, `test/licence/Erc6551RegistryIntegration.t.sol`,
/// `test/licence/ConsumeWithIntent.t.sol`, and `test/licence/ProtocolFeeSettlement.t.sol`,
/// `PRODUCTION_GAPS.md`): unlike `IntegrityKernel`'s four properties, none of the following are
/// Halmos-proven (no symbolic-execution work has been done on this contract) -- each is backed
/// only by concrete Foundry test cases, including exact-boundary and one-unit-over cases, not an
/// unbounded proof over every reachable input. Every guard below was mutation-tested (temporarily
/// disabled directly in this file, confirmed the corresponding test then fails, then restored)
/// before being trusted:
/// - **Volume cap never exceeded, and never partially consumed on revert.** `consume()` reverts,
///   with zero state change, for any call whose units would push `consumedUnits` past
///   `volumeCapTotal` -- checked at the exact boundary, one unit over, and across a cumulative
///   multi-call sequence where the final call alone would fit a fresh cap but not the remaining
///   balance.
/// - **Royalty payment is atomic with consumption.** A `consume()` call with `msg.value` below
///   the declared per-unit price for the requested units reverts before any state change;
///   `address(this).balance` (eq 16's $b_I$) grows by the FULL `msg.value` on success, including
///   overpayment -- there is no separate accounting variable and no refund path.
/// - **Expiry is enforced at both boundaries.** `consume()` succeeds at exactly
///   `licenceStartTime` and exactly `licenceEndTime`, and reverts one second outside either
///   bound.
/// - **The transfer-drain guard (eq 17) genuinely blocks a withdrawal, not merely flags one.**
///   While `armed`, `execute()` reverts -- funds unmoved -- for any native-value call that would
///   leave this account's balance below `armedCommittedBalance`; the exact boundary (down to
///   precisely the committed balance) succeeds; `disarmTransfer()` fully lifts the restriction;
///   the armed state deliberately survives an NFT transfer (a disclosed simplification, not an
///   oversight -- the new owner inherits it and may disarm themselves).
/// - **Ownership resolves dynamically and only to the current NFT holder.** `owner()`,
///   `isValidSigner()`, and every owner-gated function's authorization check track `ownerOf`
///   live; an old owner loses authority and a new owner gains it atomically on transfer, proven
///   directly rather than assumed.
/// - **The real, live canonical ERC-6551 registry's minimal-proxy mechanism works with this
///   contract as its implementation.** `Erc6551RegistryIntegration.t.sol` forks Base Sepolia and
///   proves, against the actual registry at `0x000000006551c19487814612e58FE06813775758` (not a
///   mock): `account()`'s address prediction matches what `createAccount()` actually deploys,
///   `createAccount()` is idempotent for the same parameters, and the deployed proxy enforces the
///   volume-cap and transfer-drain guards identically to a directly-constructed instance.
///
/// What this does NOT claim: no Halmos/symbolic verification (unlike `IntegrityKernel.sol`); no
/// live paymaster/bundler evidence; no permissionless adapter attestation/composition (the
/// registry hook is present but R1/R5 remain open); no marketplace or escrow
/// contract (`armTransfer`/`disarmTransfer` are bare owner-gated setters, not integrated with any
/// actual sale flow). `LicenceTermsPolicy.sol` implements the six additional Table 2 terms through
/// the typed `consumeWithTerms()` and signed-intent paths; those terms are opt-in per account and
/// are not asserted for an account whose hook is unset.
///
/// **ATCP/IP signed-intent layer** (`docs/plans/2026-08-24-phase2-atcpip-intent-format-
/// proposal.md`, `PRODUCTION_GAPS.md` §48): `consumeWithIntent()` lets the owner authorize a
/// revocable, expiring session key (`authorizeSessionKey`/`revokeSessionKey`) to sign scoped
/// `ConsumeIntent` structs (EIP-712, via OpenZeppelin's `EIP712`/`Nonces`) that ANY relayer may
/// submit on-chain -- the signer authorizes the action, not the caller. It remains a standalone
/// EIP-712 relaying path; the separate `validateUserOp()` path below is the literal account-side
/// ERC-4337 validation route and does not reinterpret `consumeWithIntent()` as a UserOperation.
///
/// **ERC-4337 account path:** `validateUserOp()` accepts the canonical EntryPoint v0.9, verifies
/// an owner or authorized session-key signature over `userOpHash`, pays missing prefund, and binds
/// the exact `execute()` calldata to a one-transaction hand-off. Owner UserOperations retain the
/// ERC-6551 CALL surface; session-key UserOperations are restricted to a self-call of
/// `consume(uint256)`. The nested self-call is the mechanism by which a UserOperation sends the
/// account's own balance as royalty. This proves account-side validation and execution binding;
/// A separate `LicencePaymaster` provides allowlisted sponsorship plumbing; neither contract alone
/// provides a live bundler transaction or production sponsorship evidence.
///
/// **Settlement integration guarantee** (`docs/plans/2026-08-24-phase2-settlement-integration-
/// proposal.md`, `PRODUCTION_GAPS.md` section 49): this slice implements only eq (12) protocol-fee
/// term phi as one immutable flat basis-point split on `royaltyDue`. The fee is computed from
/// the required units-times-price amount, never from `msg.value`, so overpayment does not inflate
/// the fee and the entire excess remains in this account. The split is settled inside the same
/// `_consume()` transition used by both `consume()` and `consumeWithIntent()`; if the recipient
/// transfer fails, the whole call reverts with no consumed-unit state change and no retained
/// funds. `protocolFeeBps == 0` is a valid no-fee configuration, including a zero recipient.
/// `LicenceEconomy.sol` provides the separate fee-router layer for adapter-author shares,
/// staking yield, buy-back/burn, treasury allocation, and delayed fee-share governance. This
/// account does not force every licence to use that router; its immutable recipient remains an
/// explicit deployment choice, and no fee applies to `execute()` withdrawals.
///
/// **Kernel hook** (`ILicenceHook.sol`, `PRODUCTION_GAPS.md` §51): an optional, immutable
/// `hook` -- whitepaper §5.3's "the same [kernel] mechanism serves both" claim, scoped down to
/// a single additive precondition rather than the full ERC-7579/whitepaper-§6 adapter-registry
/// architecture. `preConsume` is called on `hook` (if set) AFTER this contract's own volume-cap/
/// royalty/expiry checks already passed and BEFORE any state change, receiving the resolved
/// consumer (owner for `consume()`, the recovered EIP-712 signer for `consumeWithIntent()` --
/// never merely `msg.sender`) and the units/royalty about to be committed. `address(0)` disables
/// it, matching `trackedToken`'s own convention. See `ILicenceHook.sol` for what this
/// deliberately does NOT claim: not swappable/composable, no declared gas bound, no
/// ERC-7579/whitepaper-§6 adapter-registry semantics. Reference implementation:
/// `ReputationFloorLicenceHook.sol`, reading `ReputationRegistry.effectiveScore` LIVE (no
/// epoch-snapshot cache, unlike `IntegrityKernel`'s own reputation check -- disclosed design
/// choice, see that contract's own NatSpec).
///
/// **Phase III adapter registry** (`AdapterRegistry.sol`, `PRODUCTION_GAPS.md` §53): a SECOND,
/// independent, additive precondition slot -- `registryHook`/`registryAdapter`, both immutable,
/// `address(registryHook) == address(0)` disables it. Deliberately NOT a replacement for `hook`
/// above; `ILicenceHook` and `IAdapter` are different interfaces by design (see
/// `docs/design/phase3-adapter-encoding-strategy-2026-08-25.md`'s own open question on whether
/// they should ever merge -- not resolved here). When enabled, `_consume()` calls
/// `registryHook.evaluate(registryAdapter, consumer, royaltyDue)` AFTER `hook` (if also set),
/// both additive, both able to independently reject. Reverts with whatever `AdapterRegistry.
/// evaluate` itself reverts with -- see that contract's own NatSpec for the exact
/// adapter-rejection-vs-gas-bound-exceeded distinction and its disclosed limitation.
contract LicenceAccount is IERC6551Account, IAccount, EIP712, Nonces {
    error NotAuthorized(address caller);
    error UnsupportedOperation(uint8 operation);
    error LicenceNotYetActive(uint256 startTime, uint256 currentTime);
    error LicenceExpired(uint256 endTime, uint256 currentTime);
    error VolumeCapExceeded(uint256 requested, uint256 remaining);
    error InsufficientRoyalty(uint256 required, uint256 provided);
    error ZeroUnits();
    error TransferArmedWithdrawalBlocked(uint256 wouldRemain, uint256 committed);
    error ExecutionFailed(bytes returndata);
    error ZeroVolumeCap();
    error ZeroTokenContract();
    error StartNotBeforeEnd(uint256 startTime, uint256 endTime);
    error ZeroSessionKey();
    error SessionKeyExpiryInPast(uint256 expiry, uint256 currentTime);
    error UnauthorizedSigner(address signer);
    error IntentExpired(uint256 expiry, uint256 currentTime);
    error IntentDomainMismatch(address expected, address actual);
    error ZeroFeeRecipient(uint256 feeBps);
    error ZeroRegistryAdapter();
    error ProtocolFeeTransferFailed(bytes returndata);
    error UserOperationCallDataMismatch();
    error SessionKeyCannotExecuteArbitraryCall();
    error PrefundPaymentFailed();

    event Consumed(uint256 units, uint256 royaltyPaid, uint256 totalConsumed);
    event TransferArmed(uint256 committedBalance);
    event TransferDisarmed();
    event Withdrawn(address indexed to, uint256 value);
    event SessionKeyAuthorized(address indexed key, uint256 expiry);
    event SessionKeyRevoked(address indexed key);
    event ProtocolFeeSettled(address indexed recipient, uint256 amount);

    /// @dev keccak256("ConsumeIntent(address account,uint256 units,uint256 nonce,uint256 expiry)")
    bytes32 public constant CONSUME_INTENT_TYPEHASH =
        keccak256("ConsumeIntent(address account,uint256 units,uint256 nonce,uint256 expiry)");

    bytes32 public constant TERMS_CONSUME_INTENT_TYPEHASH = keccak256(
        "TermsConsumeIntent(address account,uint256 units,uint256 nonce,uint256 expiry,bytes32 purposeHash,bool derivative,bytes32 priorMemoryHead,bytes32 nextMemoryHead,uint256 memorySequence,bytes32 evidenceHash)"
    );

    struct ConsumeIntent {
        address account;
        uint256 units;
        uint256 nonce;
        uint256 expiry;
    }

    struct TermsConsumeIntent {
        address account;
        uint256 units;
        uint256 nonce;
        uint256 expiry;
        bytes32 purposeHash;
        bool derivative;
        bytes32 priorMemoryHead;
        bytes32 nextMemoryHead;
        uint256 memorySequence;
        bytes32 evidenceHash;
    }

    // --- ATCP/IP session keys: owner-authorized, revocable, expiring signers scoped to
    // ConsumeIntent signing only -- never able to call execute()/armTransfer() directly, since
    // those remain gated to msg.sender == owner().
    mapping(address key => uint256 expiry) public sessionKeyExpiry;

    // --- ERC-6551 context -- see this contract's own top-level NatSpec for why these are
    // immutable rather than read via bytecode introspection.
    uint256 private immutable _chainId;
    address public immutable tokenContractAddr;
    uint256 public immutable tokenIdValue;

    // --- licence terms, immutable, one per deployed instance
    uint256 public immutable volumeCapTotal;
    uint256 public immutable royaltyPricePerUnitWei;
    uint256 public immutable licenceStartTime;
    uint256 public immutable licenceEndTime;

    // --- settlement integration (eq 12's fee term phi, PRODUCTION_GAPS.md #49): a single flat
    // protocol fee, split atomically at settlement time. protocolFeeBps == 0 is a valid
    // no-fee configuration.
    address public immutable protocolFeeRecipient;
    uint256 public immutable protocolFeeBps;

    // --- kernel hook (ILicenceHook.sol, whitepaper §5.3 "the same mechanism serves both"):
    // a single, immutable precondition hook, address(0) disables it. Not swappable/composable --
    // see ILicenceHook's own doc comment for exactly what this does and does not claim.
    ILicenceHook public immutable hook;

    // --- Phase III adapter registry (PRODUCTION_GAPS.md §52/§53): a SECOND, independent,
    // additive precondition slot alongside `hook` above -- deliberately not a replacement.
    // `hook`'s ILicenceHook interface and IAdapter are different by design (see
    // docs/design/phase3-adapter-encoding-strategy-2026-08-25.md's own open question on whether
    // they should ever merge); this is not that merge. address(registryHook) == address(0)
    // disables this slot entirely, same convention as `hook` and `trackedToken` elsewhere in this
    // codebase. When enabled, `_consume()` calls
    // `registryHook.evaluate(registryAdapter, consumer, royaltyDue)` -- an adapter registered
    // there sees the consumer as `subject` and the royalty due as `amount`, mirroring
    // SpendBudgetAdapter's own parameter shape.
    AdapterRegistry public immutable registryHook;
    address public immutable registryAdapter;

    // One-transaction validation-to-execution hand-off for ERC-4337. EntryPoint validation
    // binds the exact execute calldata and signer before the execution call is accepted.
    bytes32 private _validatedUserOpCallHash;
    address private _validatedUserOpSigner;
    bool private _entryPointExecution;

    // --- live state
    uint256 public consumedUnits;
    uint256 public state;

    // --- transfer-drain guard (eq 17)
    bool public armed;
    uint256 public armedCommittedBalance;

    constructor(
        address tokenContractAddr_,
        uint256 tokenIdValue_,
        uint256 volumeCapTotal_,
        uint256 royaltyPricePerUnitWei_,
        uint256 licenceStartTime_,
        uint256 licenceEndTime_,
        address protocolFeeRecipient_,
        uint256 protocolFeeBps_,
        ILicenceHook hook_,
        AdapterRegistry registryHook_,
        address registryAdapter_
    ) EIP712("LicenceAccount", "1") {
        if (address(registryHook_) != address(0) && registryAdapter_ == address(0)) {
            revert ZeroRegistryAdapter();
        }
        if (tokenContractAddr_ == address(0)) revert ZeroTokenContract();
        if (volumeCapTotal_ == 0) revert ZeroVolumeCap();
        if (licenceStartTime_ >= licenceEndTime_) revert StartNotBeforeEnd(licenceStartTime_, licenceEndTime_);
        if (protocolFeeBps_ > 0 && protocolFeeRecipient_ == address(0)) revert ZeroFeeRecipient(protocolFeeBps_);

        _chainId = block.chainid;
        tokenContractAddr = tokenContractAddr_;
        tokenIdValue = tokenIdValue_;
        volumeCapTotal = volumeCapTotal_;
        royaltyPricePerUnitWei = royaltyPricePerUnitWei_;
        licenceStartTime = licenceStartTime_;
        licenceEndTime = licenceEndTime_;
        protocolFeeRecipient = protocolFeeRecipient_;
        protocolFeeBps = protocolFeeBps_;
        hook = hook_;
        registryHook = registryHook_;
        registryAdapter = registryAdapter_;
    }

    receive() external payable {}

    /// @notice Canonical ERC-4337 v0.9 EntryPoint used by this account.
    /// @dev Chain-specific EntryPoint deployments require a separately-versioned account.
    function entryPoint() public pure returns (IEntryPoint) {
        return ERC4337Utils.ENTRYPOINT_V09;
    }

    /// @notice Validates an ERC-4337 UserOperation signed by the current NFT owner or an
    /// authorized session key. Session keys are restricted to a self-call of `consume(uint256)`;
    /// owner signatures retain the normal ERC-6551 CALL surface.
    /// @dev Stores only a one-transaction authorization hand-off. `execute()` must be called by
    /// the canonical EntryPoint with byte-identical calldata, then clears the hand-off.
    function validateUserOp(PackedUserOperation calldata userOp, bytes32 userOpHash, uint256 missingAccountFunds)
        external
        returns (uint256 validationData)
    {
        if (msg.sender != address(entryPoint())) revert NotAuthorized(msg.sender);
        if (userOp.sender != address(this)) return ERC4337Utils.SIG_VALIDATION_FAILED;
        if (userOp.callData.length < 4 || bytes4(userOp.callData) != this.execute.selector) {
            return ERC4337Utils.SIG_VALIDATION_FAILED;
        }

        (address to, uint256 value, bytes memory data, uint8 operation) = abi.decode(
            userOp.callData[4:], (address, uint256, bytes, uint8)
        );
        (address signer, ECDSA.RecoverError recoverError,) = ECDSA.tryRecover(userOpHash, userOp.signature);
        if (recoverError != ECDSA.RecoverError.NoError) return ERC4337Utils.SIG_VALIDATION_FAILED;

        bool ownerSigner = signer == owner();
        bool sessionSigner = _isAuthorizedSessionKey(signer);
        if (!ownerSigner && !sessionSigner) return ERC4337Utils.SIG_VALIDATION_FAILED;

        if (sessionSigner && !ownerSigner) {
            if (to != address(this) || operation != 0 || data.length < 4 || bytes4(data) != this.consume.selector) {
                return ERC4337Utils.SIG_VALIDATION_FAILED;
            }
            // `value` is deliberately not trusted here; consume() performs the authoritative
            // royalty, expiry, and volume checks during execution.
            value;
        }

        _validatedUserOpCallHash = keccak256(userOp.callData);
        _validatedUserOpSigner = signer;
        if (missingAccountFunds > 0) {
            (bool prefundSent,) = payable(msg.sender).call{value: missingAccountFunds}("");
            if (!prefundSent) revert PrefundPaymentFailed();
        }
        return ERC4337Utils.SIG_VALIDATION_SUCCESS;
    }

    /// @notice The current licensee -- whoever holds the licence NFT right now. ERC-6551
    /// authority resolves DYNAMICALLY through this, not through any signer this contract stores
    /// itself; transferring the NFT atomically transfers command of everything this account
    /// holds (whitepaper §5.2, consequence 2).
    function owner() public view returns (address) {
        return IERC721(tokenContractAddr).ownerOf(tokenIdValue);
    }

    function token() external view returns (uint256 chainId, address tokenContract, uint256 tokenId) {
        return (_chainId, tokenContractAddr, tokenIdValue);
    }

    function isValidSigner(address signer, bytes calldata) external view returns (bytes4 magicValue) {
        if (signer == owner()) {
            return IERC6551Account.isValidSigner.selector;
        }
        return bytes4(0);
    }

    /// @notice The metered-consumption entry point: pays royalty and depletes the volume meter
    /// atomically, or reverts. Any of the three checks (expiry, volume cap, royalty) failing
    /// reverts the WHOLE call -- no partial consumption, matching whitepaper §7.1's "payment
    /// without release and release without payment are both unrepresentable."
    /// @dev Order matters for gas (cheapest checks first) but not for correctness -- every path
    /// reverts before any state change if ANY check fails, verified by
    /// `test_consumeRevertsBeforeAnyStateChange_*` in the test suite, not merely assumed from
    /// the order these checks are written in.
    function consume(uint256 units) external payable returns (uint256 royaltyPaid) {
        if (msg.sender == owner()) return _consume(units, msg.sender);
        if (msg.sender == address(this) && _entryPointExecution) return _consume(units, _validatedUserOpSigner);
        revert NotAuthorized(msg.sender);
    }

    /// @notice Typed consumption path for field-of-use, licensee, exclusivity, derivative-rights,
    /// assurance-tier, and memory-continuity policy enforcement.
    function consumeWithTerms(uint256 units, LicenceTermsContext calldata context)
        external
        payable
        returns (uint256 royaltyPaid)
    {
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        return _consumeWithTerms(units, msg.sender, context);
    }

    /// @notice The ATCP/IP entry point: any relayer may submit a `ConsumeIntent` signed off-chain
    /// by the owner or a currently-authorized session key. The SIGNER, not `msg.sender`, is what
    /// authorizes this call -- matching whitepaper §7.1's "sign scoped ATCP/IP request" step,
    /// deliberately allowing open relaying rather than gating this function to a specific caller.
    /// @dev Enforces, in order: domain binding (`intent.account` must be THIS contract, not
    /// merely a correctly-shaped signature replayed from another licence account), intent
    /// expiry, signer authorization (owner or an unexpired, non-revoked session key), and
    /// nonce replay-protection (`Nonces.useCheckedNonce`, keyed to the recovered signer, not
    /// `msg.sender`) -- before falling through to the exact same volume-cap/royalty/expiry
    /// enforcement `consume()` itself uses. This is additive authorization, not a parallel or
    /// weaker path.
    function consumeWithIntent(ConsumeIntent calldata intent, bytes calldata signature)
        external
        payable
        returns (uint256 royaltyPaid)
    {
        if (intent.account != address(this)) revert IntentDomainMismatch(address(this), intent.account);
        if (block.timestamp > intent.expiry) revert IntentExpired(intent.expiry, block.timestamp);

        bytes32 structHash =
            keccak256(abi.encode(CONSUME_INTENT_TYPEHASH, intent.account, intent.units, intent.nonce, intent.expiry));
        address signer = ECDSA.recover(_hashTypedDataV4(structHash), signature);

        if (signer != owner() && !_isAuthorizedSessionKey(signer)) revert UnauthorizedSigner(signer);

        _useCheckedNonce(signer, intent.nonce);

        return _consume(intent.units, signer);
    }

    /// @notice Open-relay typed-intent route. The owner or an authorized session key signs all
    /// six licence-term fields; any relayer may submit the intent.
    function consumeWithTermsIntent(TermsConsumeIntent calldata intent, bytes calldata signature)
        external
        payable
        returns (uint256 royaltyPaid)
    {
        if (intent.account != address(this)) revert IntentDomainMismatch(address(this), intent.account);
        if (block.timestamp > intent.expiry) revert IntentExpired(intent.expiry, block.timestamp);
        bytes32 structHash = keccak256(
            abi.encode(
                TERMS_CONSUME_INTENT_TYPEHASH,
                intent.account,
                intent.units,
                intent.nonce,
                intent.expiry,
                intent.purposeHash,
                intent.derivative,
                intent.priorMemoryHead,
                intent.nextMemoryHead,
                intent.memorySequence,
                intent.evidenceHash
            )
        );
        address signer = ECDSA.recover(_hashTypedDataV4(structHash), signature);
        if (signer != owner() && !_isAuthorizedSessionKey(signer)) revert UnauthorizedSigner(signer);
        _useCheckedNonce(signer, intent.nonce);
        LicenceTermsContext memory context = LicenceTermsContext({
            purposeHash: intent.purposeHash,
            derivative: intent.derivative,
            priorMemoryHead: intent.priorMemoryHead,
            nextMemoryHead: intent.nextMemoryHead,
            memorySequence: intent.memorySequence,
            evidenceHash: intent.evidenceHash
        });
        return _consumeWithTerms(intent.units, signer, context);
    }

    /// @notice Authorizes `key` to sign `ConsumeIntent`s on the owner's behalf until `expiry`.
    /// Owner-gated, dynamically -- only the CURRENT NFT holder may authorize a session key, same
    /// as every other owner-gated function here. A session key can only ever sign consumption
    /// intents -- it is never checked against `execute()`, `armTransfer()`, or `disarmTransfer()`.
    function authorizeSessionKey(address key, uint256 expiry) external {
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        if (key == address(0)) revert ZeroSessionKey();
        if (expiry <= block.timestamp) revert SessionKeyExpiryInPast(expiry, block.timestamp);
        sessionKeyExpiry[key] = expiry;
        emit SessionKeyAuthorized(key, expiry);
    }

    /// @notice Revokes `key` immediately, regardless of its previously-set expiry.
    function revokeSessionKey(address key) external {
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        delete sessionKeyExpiry[key];
        emit SessionKeyRevoked(key);
    }

    function _isAuthorizedSessionKey(address key) internal view returns (bool) {
        uint256 expiry = sessionKeyExpiry[key];
        return expiry != 0 && block.timestamp <= expiry;
    }

    function _consume(uint256 units, address consumer) internal returns (uint256 royaltyPaid) {
        LicenceTermsContext memory emptyContext;
        return _consumeCore(units, consumer, false, emptyContext);
    }

    function _consumeWithTerms(uint256 units, address consumer, LicenceTermsContext memory context)
        internal
        returns (uint256 royaltyPaid)
    {
        return _consumeCore(units, consumer, true, context);
    }

    function _consumeCore(uint256 units, address consumer, bool hasTerms, LicenceTermsContext memory context)
        internal
        returns (uint256 royaltyPaid)
    {
        if (units == 0) revert ZeroUnits();
        if (block.timestamp < licenceStartTime) revert LicenceNotYetActive(licenceStartTime, block.timestamp);
        if (block.timestamp > licenceEndTime) revert LicenceExpired(licenceEndTime, block.timestamp);

        uint256 remaining = volumeCapTotal - consumedUnits;
        if (units > remaining) revert VolumeCapExceeded(units, remaining);

        uint256 royaltyDue = units * royaltyPricePerUnitWei;
        if (msg.value < royaltyDue) revert InsufficientRoyalty(royaltyDue, msg.value);

        // Kernel hook (ILicenceHook.sol): an additive precondition, checked AFTER this contract's
        // own checks above already passed, BEFORE any state change below. Reverts propagate
        // directly -- no partial consumption, same discipline as every other check here.
        if (address(hook) != address(0)) {
            if (hasTerms) {
                ILicenceTermsHook(address(hook)).preConsumeWithTerms(address(this), consumer, units, royaltyDue, context);
            } else {
                hook.preConsume(address(this), consumer, units, royaltyDue);
            }
        }

        // Phase III adapter registry (PRODUCTION_GAPS.md §53): a SECOND, independent additive
        // precondition, same placement discipline as `hook` above -- after this contract's own
        // checks, before any state change. Reverts with whatever AdapterRegistry.evaluate itself
        // reverts with (the registered adapter's own reason, or AdapterExceededGasBound).
        if (address(registryHook) != address(0)) {
            registryHook.evaluate(registryAdapter, consumer, royaltyDue);
        }

        consumedUnits += units;
        state += 1;

        // Settlement integration (eq 12's fee term phi): the fee is computed off royaltyDue (the
        // REQUIRED amount for the units actually consumed), never off msg.value -- an overpaying
        // caller's excess lands entirely in this account's own balance, unaffected by the fee
        // rate, exactly as it did before this fee existed. Settled atomically in this same call:
        // if the fee transfer fails, the whole consumption reverts (eq 12 -- a transition where
        // the fee leg fails is a leak, not representable), matching this contract's own
        // no-partial-consumption discipline.
        if (protocolFeeBps > 0) {
            uint256 feeAmount = (royaltyDue * protocolFeeBps) / 10_000;
            (bool feeSuccess, bytes memory feeReturndata) = protocolFeeRecipient.call{value: feeAmount}("");
            if (!feeSuccess) revert ProtocolFeeTransferFailed(feeReturndata);
            emit ProtocolFeeSettled(protocolFeeRecipient, feeAmount);
        }

        emit Consumed(units, msg.value, consumedUnits);
        return msg.value;
    }

    /// @notice Arms the transfer-drain guard: while armed, `execute()` may never let this
    /// account's balance fall below `committedBalance` (eq 17). Owner-gated -- the current
    /// licensee arms it themselves as part of agreeing to a sale, before the buyer's payment is
    /// finalized elsewhere. Does NOT auto-clear on an actual NFT transfer -- see this contract's
    /// own top-level design note and the proposal doc's own disclosed simplification: a new
    /// owner inherits an armed state and may call `disarmTransfer()` themselves.
    function armTransfer(uint256 committedBalance) external {
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        armed = true;
        armedCommittedBalance = committedBalance;
        emit TransferArmed(committedBalance);
    }

    function disarmTransfer() external {
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        armed = false;
        armedCommittedBalance = 0;
        emit TransferDisarmed();
    }

    /// @notice The general ERC-6551 execution entry point -- how the current licensee withdraws
    /// accrued royalty balance, or performs any other action as this account. `operation` must
    /// be `0` (CALL); anything else reverts. This is where the transfer-drain guard (eq 17) is
    /// actually enforced: while armed, a call that would move native value out and leave the
    /// account below `armedCommittedBalance` reverts, not merely gets flagged.
    function execute(address to, uint256 value, bytes calldata data, uint8 operation)
        external
        payable
        returns (bytes memory)
    {
        bool fromEntryPoint = msg.sender == address(entryPoint());
        if (!fromEntryPoint && msg.sender != owner()) revert NotAuthorized(msg.sender);
        if (fromEntryPoint && keccak256(msg.data) != _validatedUserOpCallHash) {
            revert UserOperationCallDataMismatch();
        }
        if (operation != 0) revert UnsupportedOperation(operation);

        if (fromEntryPoint && _validatedUserOpSigner != owner()) {
            if (to != address(this) || data.length < 4 || bytes4(data) != this.consume.selector) {
                revert SessionKeyCannotExecuteArbitraryCall();
            }
        }

        if (armed && value > 0) {
            uint256 balanceAfter = address(this).balance - value;
            if (balanceAfter < armedCommittedBalance) {
                revert TransferArmedWithdrawalBlocked(balanceAfter, armedCommittedBalance);
            }
        }

        state += 1;
        if (fromEntryPoint) _entryPointExecution = true;
        (bool success, bytes memory returndata) = to.call{value: value}(data);
        if (fromEntryPoint) {
            _entryPointExecution = false;
            delete _validatedUserOpCallHash;
            delete _validatedUserOpSigner;
        }
        if (!success) revert ExecutionFailed(returndata);
        if (value > 0) emit Withdrawn(to, value);
        return returndata;
    }
}
