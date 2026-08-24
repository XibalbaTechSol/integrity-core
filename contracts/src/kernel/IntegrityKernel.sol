// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC7579Hook, MODULE_TYPE_HOOK} from "@openzeppelin/contracts/interfaces/draft-IERC7579.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {ReputationRegistry} from "../oracle/ReputationRegistry.sol";

/// @title IntegrityKernel
/// @notice Phase I tracer-bullet slice (docs/plans/2026-08-17-phase1-tracer-bullet-proposal.md),
/// extended with a second reference adapter
/// (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md), then with reputation
/// epoch-snapshotting (docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md).
/// @dev NOT the full Phase I `IntegrityKernel` the plan describes. This kernel enforces exactly
/// TWO conjunctive conditions -- a native-value spend budget (per-operation and cumulative) and
/// a reputation floor read from a locally cached snapshot of `ReputationRegistry.effectiveScore`
/// -- and nothing else. It is bound to exactly one account at construction (immutable, no
/// rebind) and is intended to be installed exactly once, atomically, by that account's own
/// constructor.
///
/// **Reputation and assurance-tier state are cached, not read live, per
/// `docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md`.** `refreshReputationSnapshot`
/// is permissionless -- anyone may pay to refresh it, not only the bound account -- and reads
/// `reputationRegistry.scores(boundAccount)` once (a single external call returning the whole
/// struct) rather than the two separate calls `effectiveScore`/`isZkBoosted` each require.
/// `preCheck` reads the cache and FAILS CLOSED if it is older than `epochLengthSeconds`: a stale
/// snapshot reverts, it is never silently trusted. This is a real, disclosed tradeoff, not a free
/// resolution -- WITHIN an epoch, reputation is not merely "possibly a little stale," it is
/// completely unenforced; the only thing bounding damage during that window is the budget check.
/// `epochLengthSeconds` is capped at `MAX_EPOCH_LENGTH_SECONDS` specifically so "epoch-snapshotted
/// reputation" cannot be truthfully claimed by a deployment that sets an unreasonably long epoch
/// and means, in practice, "never re-checked." See the proposal doc's "Real risk worth naming
/// explicitly" section -- found via an independent adversarial review, not caught at design time.
///
/// **Deployment invariant, not just a recommendation: `epochLengthSeconds` on THIS kernel must be
/// `>= moduleActionTimelockSeconds` on the bound account, if that account uses the timelocked
/// kernel-swap governance mechanism** (`IntegrityAccount.proposeKernelSwap`/
/// `executeKernelSwap`). If the timelock outlives the epoch, a fully-vested swap's uninstall half
/// (mediated by THIS kernel's own `preCheck`) can revert `SnapshotStale` for a reason that has
/// nothing to do with reputation actually being bad, and a freshly-installed replacement kernel
/// (whose own snapshot was taken at ITS construction time, before the wait) can be immediately
/// stale-on-arrival, silently bricking the account's very first post-swap `execute()` call until
/// a second refresh happens. Neither failure is destructive (a reverted swap leaves the prior
/// state intact; `refreshReputationSnapshot` is cheap and permissionless), but both are easy to
/// mistake for a reputation problem when they are actually a parameter-choice problem. This is
/// also found by adversarial review, not by design-time analysis.
///
/// **As of 2026-08-19, `IntegrityAccount` enforces this at the one point a
/// mismatched kernel could actually be installed** (`_checkEpochCompatibility`, called from its
/// constructor and every kernel-swap-proposal path) -- WITH a disclosed, deliberate gap: the
/// check is a `try`/`catch` probe of this kernel's `epochLengthSeconds()`, so it only applies to
/// a `newKernel` that implements that function at all; a hypothetical future kernel with no
/// epoch concept is not required to, and is not rejected. See that contract's own
/// `moduleActionTimelockSeconds` doc comment for the full statement. This is no longer purely "a
/// deploy scripts and operators must respect this" discipline for THIS kernel's own case, but the
/// account contract, not this one, is where that enforcement actually lives.
///
/// Guarantee this kernel actually provides, stated precisely (do not extend this claim beyond
/// what's written here): while installed and while the bound account's `execute()` is invoked
/// with `(CALLTYPE_SINGLE, EXECTYPE_DEFAULT)` (the only mode the paired account contract
/// permits), (1) a single execution can never move more than `perOpBudgetWei` of the account's
/// own native-token balance out, and the running total across all such executions can never
/// exceed `cumulativeBudgetWei`; (1b) if `trackedToken != address(0)`, the same two-tier budget
/// (`tokenPerOpBudgetWei`/`tokenCumulativeBudgetWei`) independently applies to
/// `trackedToken.balanceOf(boundAccount)`, read LIVE on every check (never cached -- see the
/// contract-level "declared multi-asset value conservation" note below for why this cannot use
/// the same epoch-snapshot trick reputation does); AND (2) no execution proceeds at all while the
/// CACHED `effectiveScore(boundAccount) < minEffectiveScore`, where the cache is at most
/// `epochLengthSeconds` old (older, and the call reverts rather than proceeding on stale data).
/// This kernel does NOT verify calldata content, does NOT constrain any asset other than native
/// ETH and the single, immutably-declared `trackedToken` (any other ERC-20/ERC-721/other asset
/// movement inside the wrapped call remains completely unconstrained), does NOT enforce anything
/// about batch/delegatecall/executor/fallback paths (the paired account is responsible for making
/// those paths unreachable, not this kernel), does NOT implement module governance (`onUninstall`
/// is intentionally left reachable only via the bound account's own, separately governed,
/// module-mutation path), and does NOT reason about how `effectiveScore` was computed or whether
/// the oracle pushing it is honest -- it trusts that number exactly as far as `ReputationRegistry`
/// itself does, subject to the staleness window above.
///
/// **Declared multi-asset value conservation** (`docs/plans/2026-08-24-phase1-declared-asset-
/// conservation-proposal.md`): a single additional ERC-20 `trackedToken`, immutable, set at
/// construction, `address(0)` meaning "no additional token tracked" (preserves the original
/// native-only behavior). Unlike the reputation/assurance-tier checks above, this CANNOT be
/// cached -- value conservation is a hard invariant per the whitepaper's own §4.7.1 ("never enter
/// grace... fail-closed in every state"), so a cached balance would silently misstate the actual
/// conserved quantity rather than merely widen a staleness window on a soft precondition. Every
/// check reads `balanceOf` live, in both `preCheck` and `postCheck`, exactly as the native-ETH
/// budget already does for `boundAccount.balance`. Deliberately scoped to exactly ONE additional
/// token, not a general list -- `preCheck` was already gas-constrained before this addition (see
/// the proposal doc's gas-checkpoint discussion); more than one tracked token was not attempted
/// without first measuring this one. Does NOT support ERC-721 or any non-fungible asset, and does
/// NOT protect against fee-on-transfer/rebasing token behavior beyond correctly bounding the
/// *observed* balance delta (which is what equation (12) actually requires) -- a token whose
/// balance moves by more than the wrapped call's own transfer amount (e.g. a rebase) is still
/// correctly checked against the observed delta, not the nominal one.
///
/// **Real, disclosed finding: with `trackedToken` enabled, `preCheck` measures OVER the
/// whitepaper's own Table 4 ceiling (`<=40k`), not under it.** A cold `trackedToken.balanceOf`
/// read (the representative production case -- see
/// `test_preCheckGasExceedsPaperTable4BudgetWithTrackedTokenLiveRead`'s own comment for why an
/// earlier, same-transaction-mint measurement of ~25.8k was an unrepresentative warm-storage
/// artifact) puts `preCheck` at ~41k, against the ~35.5k the disabled-token path itself measures
/// cold. This crossing was named as a real possibility, not a surprise, before this feature was
/// built (`docs/plans/2026-08-24-phase1-declared-asset-conservation-proposal.md`'s own dependency
/// inventory) -- value conservation is a hard invariant (§4.7.1) and therefore cannot reuse the
/// epoch-snapshotting cache that rescued the reputation/assurance-tier checks from their own,
/// earlier crossing. **No mitigation has been attempted within this slice's scope.** This is an
/// open finding requiring its own decision, not a resolved one.
contract IntegrityKernel is IERC7579Hook {
    error Unauthorized(address caller);
    error AlreadyArmed();
    error NotArmed();
    error PerOperationBudgetExceeded(uint256 spent, uint256 budget);
    error CumulativeBudgetExceeded(uint256 spentSoFar, uint256 attempted, uint256 budget);
    error TokenPerOperationBudgetExceeded(uint256 spent, uint256 budget);
    error TokenCumulativeBudgetExceeded(uint256 spentSoFar, uint256 attempted, uint256 budget);
    error ZeroAccount();
    error ZeroBudget();
    error ZeroTokenBudget();
    error ZeroReputationRegistry();
    error ZeroMinEffectiveScore();
    error ZeroEpochLength();
    error EpochLengthTooLong(uint256 requested, uint256 maxAllowed);
    error BoostConstantsMismatch(
        uint256 localBps, uint256 registryBps, uint256 localDenominator, uint256 registryDenominator
    );
    error ReputationBelowFloor(uint256 score, uint256 minRequired);
    error AssuranceTierNotMet(address account);
    error SnapshotStale(uint256 snapshotTakenAt, uint256 currentTime, uint256 epochLengthSeconds);

    event ReputationSnapshotRefreshed(uint256 score, bool zkBoosted, uint256 takenAt);

    address public immutable boundAccount;
    uint256 public immutable perOpBudgetWei;
    uint256 public immutable cumulativeBudgetWei;

    /// @dev Declared multi-asset value conservation (docs/plans/2026-08-24-phase1-declared-
    /// asset-conservation-proposal.md). `address(0)` means no additional token is tracked --
    /// every existing deployment/test that doesn't pass a real token sees zero behavior change.
    IERC20 public immutable trackedToken;
    uint256 public immutable tokenPerOpBudgetWei;
    uint256 public immutable tokenCumulativeBudgetWei;
    uint256 public tokenCumulativeSpentWei;

    /// @dev Second reference adapter (docs/plans/2026-08-17-phase1-reputation-adapter-proposal.md):
    /// a conjunctive precondition, not a conserved quantity -- reputation cannot change DURING
    /// the wrapped call in any way this kernel needs to re-verify after the fact, so this is
    /// checked once in `preCheck` and never touched in `postCheck`. The subject checked is
    /// always `boundAccount` itself, matching the real system's intended design (a real
    /// `IntegrityAccount` registers itself as `primitives.sovereignAgent`), never a separate
    /// configurable address.
    ReputationRegistry public immutable reputationRegistry;
    uint256 public immutable minEffectiveScore;

    /// @dev Mirrors `ReputationRegistry.ZK_BOOST_BPS`/`BPS_DENOMINATOR` locally so
    /// `refreshReputationSnapshot` can derive both cached values from a SINGLE external call to
    /// `scores(address)` instead of paying for separate `effectiveScore`/`isZkBoosted` calls (each
    /// of which would re-read the same underlying storage via its own external call). These are
    /// `constant` on `ReputationRegistry`, not `immutable` -- fixed at that contract's compile
    /// time, so mirroring them here is safe for a given deployed `ReputationRegistry` bytecode --
    /// **verified at construction time**, not just asserted: the constructor reads the real
    /// `reputationRegistry.ZK_BOOST_BPS()`/`BPS_DENOMINATOR()` once and reverts
    /// `BoostConstantsMismatch` if they diverge from these local values, so a future
    /// `ReputationRegistry` deployment with different constants fails loudly at deploy time rather
    /// than silently producing wrong cached scores forever. (An earlier version of this guard was
    /// only a test comparing two hardcoded literals against each other, which verified nothing
    /// about this kernel at all -- caught by an independent adversarial review.)
    uint256 private constant ZK_BOOST_BPS = 11_500;
    uint256 private constant BPS_DENOMINATOR = 10_000;

    /// @dev Reputation epoch-snapshotting (docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md).
    /// `epochLengthSeconds` is immutable -- the staleness window itself cannot be widened or
    /// narrowed post-deployment, closing off "govern the freshness requirement" as an attack
    /// surface, same reasoning as the account's own `moduleActionTimelockSeconds`. Capped at
    /// `MAX_EPOCH_LENGTH_SECONDS` -- see the contract-level doc comment above for why an unbounded
    /// epoch would make "epoch-snapshotted" a claim without content.
    uint256 public constant MAX_EPOCH_LENGTH_SECONDS = 7 days;
    uint256 public immutable epochLengthSeconds;
    uint256 public snapshotScore;
    bool public snapshotIsZkBoosted;
    uint256 public snapshotTakenAt;

    uint256 public cumulativeSpentWei;

    /// @dev Reentrancy/replay guard (see docs/design/phase1-slice-dependency-inventory-2026-08-17.md
    /// for why this is necessary, not decorative): without it, a call that reenters `execute()`
    /// before the outer call's `postCheck` has run could get its own preCheck/postCheck pair
    /// evaluated against `cumulativeSpentWei` before the outer call's spend is accounted for,
    /// letting two nested calls each independently pass a budget check that their combined spend
    /// would fail.
    bool public armed;

    modifier onlyBoundAccount() {
        if (msg.sender != boundAccount) revert Unauthorized(msg.sender);
        _;
    }

    constructor(
        address boundAccount_,
        uint256 perOpBudgetWei_,
        uint256 cumulativeBudgetWei_,
        address reputationRegistry_,
        uint256 minEffectiveScore_,
        uint256 epochLengthSeconds_,
        address trackedToken_,
        uint256 tokenPerOpBudgetWei_,
        uint256 tokenCumulativeBudgetWei_
    ) {
        if (boundAccount_ == address(0)) revert ZeroAccount();
        if (perOpBudgetWei_ == 0 || cumulativeBudgetWei_ == 0) revert ZeroBudget();
        if (reputationRegistry_ == address(0)) revert ZeroReputationRegistry();
        if (minEffectiveScore_ == 0) revert ZeroMinEffectiveScore();
        if (epochLengthSeconds_ == 0) revert ZeroEpochLength();
        if (epochLengthSeconds_ > MAX_EPOCH_LENGTH_SECONDS) {
            revert EpochLengthTooLong(epochLengthSeconds_, MAX_EPOCH_LENGTH_SECONDS);
        }
        // trackedToken_ == address(0) deliberately disables this feature entirely -- the two
        // budget params are then meaningless and NOT validated, matching how a disabled feature
        // should behave (no forced non-zero values for a token that will never be checked).
        if (trackedToken_ != address(0) && (tokenPerOpBudgetWei_ == 0 || tokenCumulativeBudgetWei_ == 0)) {
            revert ZeroTokenBudget();
        }
        boundAccount = boundAccount_;
        perOpBudgetWei = perOpBudgetWei_;
        cumulativeBudgetWei = cumulativeBudgetWei_;
        trackedToken = IERC20(trackedToken_);
        tokenPerOpBudgetWei = tokenPerOpBudgetWei_;
        tokenCumulativeBudgetWei = tokenCumulativeBudgetWei_;
        ReputationRegistry registry = ReputationRegistry(reputationRegistry_);
        reputationRegistry = registry;
        minEffectiveScore = minEffectiveScore_;
        epochLengthSeconds = epochLengthSeconds_;

        // Verified once, at deploy time, not merely asserted in a test: the locally-mirrored
        // ZK_BOOST_BPS/BPS_DENOMINATOR must match the REAL bound registry's own values, or every
        // cached score this kernel ever computes silently diverges from a live effectiveScore()
        // read. One extra external call, paid once, not on the gas-constrained preCheck path.
        uint256 registryBps = registry.ZK_BOOST_BPS();
        uint256 registryDenominator = registry.BPS_DENOMINATOR();
        if (registryBps != ZK_BOOST_BPS || registryDenominator != BPS_DENOMINATOR) {
            revert BoostConstantsMismatch(ZK_BOOST_BPS, registryBps, BPS_DENOMINATOR, registryDenominator);
        }

        // Atomic initial snapshot -- the first preCheck must never special-case an empty
        // snapshot (snapshotTakenAt == 0 would otherwise always read as maximally stale).
        _refreshReputationSnapshot(registry, boundAccount_);
    }

    /// @notice Refreshes the cached reputation snapshot `preCheck` reads. Permissionless by
    /// design -- pulls only real data from `reputationRegistry`, nothing caller-supplied, so
    /// there is no manipulation surface over WHAT gets cached, only a gas cost anyone may
    /// voluntarily pay (the bound account itself, an off-chain keeper, or any other party with an
    /// interest in the account staying usable). A caller CAN influence WHEN the real registry
    /// state gets pulled in, which only ever makes the cache more current, never less accurate.
    function refreshReputationSnapshot() external {
        _refreshReputationSnapshot(reputationRegistry, boundAccount);
    }

    function _refreshReputationSnapshot(ReputationRegistry registry, address account) private {
        (uint256 baseScore,, uint256 zkBoostExpiry) = registry.scores(account);
        bool boosted = block.timestamp <= zkBoostExpiry;
        uint256 score = boosted ? (baseScore * ZK_BOOST_BPS) / BPS_DENOMINATOR : baseScore;
        snapshotScore = score;
        snapshotIsZkBoosted = boosted;
        snapshotTakenAt = block.timestamp;
        emit ReputationSnapshotRefreshed(score, boosted, block.timestamp);
    }

    // ----------------------------------------------------------------- IERC7579Module ---

    function onInstall(bytes calldata) external view onlyBoundAccount {}

    /// @dev Left callable (per IERC7579Module's interface requirement) but this slice's paired
    /// account never exposes a reachable uninstall path -- see IntegrityAccount's
    /// own module comment. Not a guarantee this kernel itself provides.
    function onUninstall(bytes calldata) external view onlyBoundAccount {}

    function isModuleType(uint256 moduleTypeId) external pure returns (bool) {
        return moduleTypeId == MODULE_TYPE_HOOK;
    }

    // ------------------------------------------------------------------- IERC7579Hook ---

    /// @dev Snapshots the bound account's native balance. Returns it ABI-encoded as `hookData`,
    /// threaded directly to `postCheck` by the account's own `withHook` modifier -- no kernel
    /// storage needed for the snapshot itself, only for the `armed` guard.
    function preCheck(address, uint256, bytes calldata) external onlyBoundAccount returns (bytes memory hookData) {
        if (armed) revert AlreadyArmed();

        // Reputation epoch-snapshotting (docs/plans/2026-08-17-phase1-reputation-snapshot-proposal.md):
        // reads the cache, never live -- this is what brings preCheck back under the whitepaper's
        // Table 4 budget. Fails closed on a stale snapshot rather than silently trusting old data;
        // `refreshReputationSnapshot()` (permissionless) is the only way past this revert.
        if (block.timestamp > snapshotTakenAt + epochLengthSeconds) {
            revert SnapshotStale(snapshotTakenAt, block.timestamp, epochLengthSeconds);
        }

        if (snapshotScore < minEffectiveScore) revert ReputationBelowFloor(snapshotScore, minEffectiveScore);

        // Third reference adapter (docs/plans/2026-08-17-phase1-assurance-tier-adapter-proposal.md):
        // also now read from the same cache, same staleness window as the score above -- kept
        // uniform deliberately, see the snapshot proposal doc's rejected-alternative section for
        // why a separately-cached raw zkBoostExpiry was considered and rejected.
        if (!snapshotIsZkBoosted) revert AssuranceTierNotMet(boundAccount);

        armed = true;
        // Declared multi-asset value conservation: the tracked token's balance must be read
        // LIVE here (never cached) since this is a hard invariant, not soft context -- see the
        // contract-level doc comment. address(trackedToken) == address(0) skips the external
        // call entirely (encodes 0, which postCheck's identical guard also skips re-reading).
        uint256 tokenBefore =
            address(trackedToken) == address(0) ? 0 : trackedToken.balanceOf(boundAccount);
        return abi.encode(boundAccount.balance, tokenBefore);
    }

    function postCheck(bytes calldata hookData) external onlyBoundAccount {
        if (!armed) revert NotArmed();
        armed = false;

        (uint256 balanceBefore, uint256 tokenBefore) = abi.decode(hookData, (uint256, uint256));
        uint256 balanceAfter = boundAccount.balance;
        uint256 spent = balanceBefore > balanceAfter ? balanceBefore - balanceAfter : 0;

        if (spent > perOpBudgetWei) revert PerOperationBudgetExceeded(spent, perOpBudgetWei);

        uint256 newCumulative = cumulativeSpentWei + spent;
        if (newCumulative > cumulativeBudgetWei) {
            revert CumulativeBudgetExceeded(cumulativeSpentWei, spent, cumulativeBudgetWei);
        }
        cumulativeSpentWei = newCumulative;

        if (address(trackedToken) != address(0)) {
            uint256 tokenAfter = trackedToken.balanceOf(boundAccount);
            uint256 tokenSpent = tokenBefore > tokenAfter ? tokenBefore - tokenAfter : 0;

            if (tokenSpent > tokenPerOpBudgetWei) {
                revert TokenPerOperationBudgetExceeded(tokenSpent, tokenPerOpBudgetWei);
            }

            uint256 newTokenCumulative = tokenCumulativeSpentWei + tokenSpent;
            if (newTokenCumulative > tokenCumulativeBudgetWei) {
                revert TokenCumulativeBudgetExceeded(tokenCumulativeSpentWei, tokenSpent, tokenCumulativeBudgetWei);
            }
            tokenCumulativeSpentWei = newTokenCumulative;
        }
    }
}
