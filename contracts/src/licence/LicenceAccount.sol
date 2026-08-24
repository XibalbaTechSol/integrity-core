// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {IERC721} from "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import {IERC6551Account} from "./IERC6551.sol";

/// @title LicenceAccount
/// @notice Phase II tracer-bullet slice
/// (`docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`): an ERC-6551
/// token-bound account representing intellectual property as a live, metered asset
/// (whitepaper §5.1-5.4). Enforces exactly THREE licence terms from Table 2 -- volume cap
/// (monotone depletion, eq 13), royalty (value conservation, eq 12), and expiry (a plain block-
/// timestamp bound) -- plus the transfer-drain guard (eq 17). The other six Table 2 terms
/// (field of use, licensee identity, exclusivity, derivative rights, assurance tier, memory
/// continuity), ATCP/IP signed intents, the adapter registry, and state channels are all
/// explicitly deferred -- see the proposal doc's own scope section.
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
/// **Concrete guarantees this slice proves** (31 Foundry tests --
/// `test/licence/LicenceAccount.t.sol` and `test/licence/Erc6551RegistryIntegration.t.sol`,
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
/// ATCP/IP signed-intent path (`consume()` is called directly, matching how Phase I's own first
/// slice used `vm.prank` before EntryPoint integration existed); no adapter registry (terms are
/// hardcoded per-instance, not compiled from an external payload); no marketplace or escrow
/// contract (`armTransfer`/`disarmTransfer` are bare owner-gated setters, not integrated with any
/// actual sale flow); and the other six Table 2 licence terms (field of use, licensee identity,
/// exclusivity, derivative rights, assurance tier, memory continuity) are unimplemented -- see
/// `docs/plans/2026-08-24-phase2-licence-account-tracer-bullet-proposal.md`'s own scope section.
contract LicenceAccount is IERC6551Account {
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

    event Consumed(uint256 units, uint256 royaltyPaid, uint256 totalConsumed);
    event TransferArmed(uint256 committedBalance);
    event TransferDisarmed();
    event Withdrawn(address indexed to, uint256 value);

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
        uint256 licenceEndTime_
    ) {
        if (tokenContractAddr_ == address(0)) revert ZeroTokenContract();
        if (volumeCapTotal_ == 0) revert ZeroVolumeCap();
        if (licenceStartTime_ >= licenceEndTime_) revert StartNotBeforeEnd(licenceStartTime_, licenceEndTime_);

        _chainId = block.chainid;
        tokenContractAddr = tokenContractAddr_;
        tokenIdValue = tokenIdValue_;
        volumeCapTotal = volumeCapTotal_;
        royaltyPricePerUnitWei = royaltyPricePerUnitWei_;
        licenceStartTime = licenceStartTime_;
        licenceEndTime = licenceEndTime_;
    }

    receive() external payable {}

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
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        if (units == 0) revert ZeroUnits();
        if (block.timestamp < licenceStartTime) revert LicenceNotYetActive(licenceStartTime, block.timestamp);
        if (block.timestamp > licenceEndTime) revert LicenceExpired(licenceEndTime, block.timestamp);

        uint256 remaining = volumeCapTotal - consumedUnits;
        if (units > remaining) revert VolumeCapExceeded(units, remaining);

        uint256 royaltyDue = units * royaltyPricePerUnitWei;
        if (msg.value < royaltyDue) revert InsufficientRoyalty(royaltyDue, msg.value);

        consumedUnits += units;
        state += 1;
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
        if (msg.sender != owner()) revert NotAuthorized(msg.sender);
        if (operation != 0) revert UnsupportedOperation(operation);

        if (armed && value > 0) {
            uint256 balanceAfter = address(this).balance - value;
            if (balanceAfter < armedCommittedBalance) {
                revert TransferArmedWithdrawalBlocked(balanceAfter, armedCommittedBalance);
            }
        }

        state += 1;
        (bool success, bytes memory returndata) = to.call{value: value}(data);
        if (!success) revert ExecutionFailed(returndata);
        if (value > 0) emit Withdrawn(to, value);
        return returndata;
    }
}
