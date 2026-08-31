// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ILicenceHook} from "./ILicenceHook.sol";
import {ILicenceTermsHook, LicenceTermsContext} from "./ILicenceTermsHook.sol";
import {ILicenceDelegationView, LicenceDelegationView} from "./ILicenceDelegationView.sol";

interface IAssuranceTierProvider {
    function assuranceTier(address subject) external view returns (uint256);
}

/// @title LicenceTermsPolicy
/// @notice Enforces the six typed Phase II licence terms omitted from the original tracer bullet.
/// @dev This is an additive hook for `LicenceAccount`. Untyped `consume()` calls are rejected when
/// this policy is installed; callers must provide the purpose, derivative-rights, and memory-chain
/// context through `consumeWithTerms()` or its signed-intent equivalent.
contract LicenceTermsPolicy is ILicenceHook, ILicenceTermsHook, ILicenceDelegationView, Ownable {
    error TermsContextRequired();
    error FieldOfUseDenied(bytes32 expected, bytes32 supplied);
    error LicenseeNotAllowed(address consumer);
    error ExclusiveLicenseeMismatch(address expected, address supplied);
    error ExclusivityLimitReached(uint256 active, uint256 maximum);
    error DerivativeRightsDenied();
    error AssuranceTierInsufficient(address consumer, uint256 actual, uint256 required);
    error MemoryPriorHeadMismatch(bytes32 expected, bytes32 supplied);
    error MemoryHeadMismatch(bytes32 expected, bytes32 supplied);
    error MemorySequenceMismatch(uint256 expected, uint256 supplied);
    error ZeroAssuranceProvider();

    bytes32 public immutable fieldOfUseHash;
    address public immutable requiredLicensee;
    bool public immutable exclusive;
    bool public immutable derivativeRights;
    IAssuranceTierProvider public immutable assuranceProvider;
    uint256 public immutable minimumAssuranceTier;
    uint256 public immutable maximumActiveLicensees;
    bytes32 public immutable initialMemoryHead;

    mapping(address licensee => bool) public allowedLicensee;
    mapping(address licensee => bool) public activeLicensee;
    mapping(address licensee => bytes32) public memoryHead;
    mapping(address licensee => uint256) public memorySequence;
    uint256 public activeLicenseeCount;
    address public exclusiveLicensee;

    event LicenseeAllowed(address indexed licensee, bool allowed);

    constructor(
        address owner_,
        bytes32 fieldOfUseHash_,
        address requiredLicensee_,
        bool exclusive_,
        bool derivativeRights_,
        IAssuranceTierProvider assuranceProvider_,
        uint256 minimumAssuranceTier_,
        uint256 maximumActiveLicensees_,
        bytes32 initialMemoryHead_
    ) Ownable(owner_) {
        if (address(assuranceProvider_) == address(0)) revert ZeroAssuranceProvider();
        fieldOfUseHash = fieldOfUseHash_;
        requiredLicensee = requiredLicensee_;
        exclusive = exclusive_;
        derivativeRights = derivativeRights_;
        assuranceProvider = assuranceProvider_;
        minimumAssuranceTier = minimumAssuranceTier_;
        maximumActiveLicensees = maximumActiveLicensees_;
        initialMemoryHead = initialMemoryHead_;
        if (requiredLicensee_ != address(0)) allowedLicensee[requiredLicensee_] = true;
    }

    function setAllowedLicensee(address licensee, bool allowed) external onlyOwner {
        allowedLicensee[licensee] = allowed;
        emit LicenseeAllowed(licensee, allowed);
    }

    /// @notice Returns the complete policy configuration and the current delegation state for
    /// `consumer` through one stable, read-only surface shared by protocol clients.
    function delegationView(address consumer) external view returns (LicenceDelegationView memory view_) {
        view_.fieldOfUseHash = fieldOfUseHash;
        view_.requiredLicensee = requiredLicensee;
        view_.exclusive = exclusive;
        view_.derivativeRights = derivativeRights;
        view_.minimumAssuranceTier = minimumAssuranceTier;
        view_.observedAssuranceTier = assuranceProvider.assuranceTier(consumer);
        view_.maximumActiveLicensees = maximumActiveLicensees;
        view_.activeLicenseeCount = activeLicenseeCount;
        view_.exclusiveLicensee = exclusiveLicensee;
        view_.consumer = consumer;
        view_.allowedLicensee = allowedLicensee[consumer];
        view_.activeLicensee = activeLicensee[consumer];
        view_.initialMemoryHead = initialMemoryHead;
        view_.memoryHead = memoryHead[consumer];
        view_.memorySequence = memorySequence[consumer];
    }

    /// @dev The untyped route cannot prove the required typed terms, so it fails closed.
    function preConsume(address, address, uint256, uint256) external pure {
        revert TermsContextRequired();
    }

    function preConsumeWithTerms(
        address account,
        address consumer,
        uint256,
        uint256,
        LicenceTermsContext calldata context
    ) external {
        if (context.purposeHash != fieldOfUseHash) revert FieldOfUseDenied(fieldOfUseHash, context.purposeHash);
        if (!allowedLicensee[consumer]) revert LicenseeNotAllowed(consumer);
        if (requiredLicensee != address(0) && consumer != requiredLicensee) {
            revert ExclusiveLicenseeMismatch(requiredLicensee, consumer);
        }
        if (exclusive) {
            if (exclusiveLicensee == address(0)) exclusiveLicensee = consumer;
            if (exclusiveLicensee != consumer) revert ExclusiveLicenseeMismatch(exclusiveLicensee, consumer);
        }
        if (!activeLicensee[consumer]) {
            if (maximumActiveLicensees > 0 && activeLicenseeCount >= maximumActiveLicensees) {
                revert ExclusivityLimitReached(activeLicenseeCount, maximumActiveLicensees);
            }
            activeLicensee[consumer] = true;
            activeLicenseeCount += 1;
        }
        if (!derivativeRights && context.derivative) revert DerivativeRightsDenied();

        uint256 actualTier = assuranceProvider.assuranceTier(consumer);
        if (actualTier < minimumAssuranceTier) {
            revert AssuranceTierInsufficient(consumer, actualTier, minimumAssuranceTier);
        }

        bytes32 expectedPrior = memoryHead[consumer];
        if (memorySequence[consumer] == 0) expectedPrior = initialMemoryHead;
        if (context.priorMemoryHead != expectedPrior) {
            revert MemoryPriorHeadMismatch(expectedPrior, context.priorMemoryHead);
        }
        uint256 expectedSequence = memorySequence[consumer] + 1;
        if (context.memorySequence != expectedSequence) {
            revert MemorySequenceMismatch(expectedSequence, context.memorySequence);
        }
        bytes32 expectedNext = keccak256(
            abi.encode(block.chainid, account, consumer, context.memorySequence, context.evidenceHash, context.priorMemoryHead)
        );
        if (context.nextMemoryHead != expectedNext) revert MemoryHeadMismatch(expectedNext, context.nextMemoryHead);
        memoryHead[consumer] = context.nextMemoryHead;
        memorySequence[consumer] = context.memorySequence;
    }
}
