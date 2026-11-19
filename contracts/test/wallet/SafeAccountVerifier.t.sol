// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { Test } from "forge-std/Test.sol";
import { SafeAccountVerifier } from "../../src/wallet/SafeAccountVerifier.sol";

contract MockSafeAccount {
    address public masterCopyAddress;
    uint256 public thresholdValue = 1;
    address[] public ownersList;
    address[] public enabledModules;
    address public fallbackHandlerAddress;
    address public guardAddress;
    bool public shouldRevert;

    address internal constant SENTINEL_MODULES = address(0x1);
    bytes32 internal constant GUARD_STORAGE_SLOT = 0x4a204f620c8c5ccdca3fd54d003badd85ba500436a431f0cbda4f558c93c34c8;
    bytes32 internal constant FALLBACK_HANDLER_STORAGE_SLOT = 0x6c9a6c4a39284e37ed1cf53d337577d14212a4870fb976a4366c693b939918d5;

    constructor(address _singleton, address _owner, address _safe7579, address _guard) {
        masterCopyAddress = _singleton;
        ownersList.push(_owner);
        enabledModules.push(_safe7579);
        fallbackHandlerAddress = _safe7579;
        guardAddress = _guard;
    }

    function setMasterCopy(address _mc) external {
        masterCopyAddress = _mc;
    }

    function setThreshold(uint256 _t) external {
        thresholdValue = _t;
    }

    function setOwners(address[] calldata _owners) external {
        ownersList = _owners;
    }

    function setModules(address[] calldata _mods) external {
        enabledModules = _mods;
    }

    function setFallbackHandler(address _handler) external {
        fallbackHandlerAddress = _handler;
    }

    function setGuard(address _guard) external {
        guardAddress = _guard;
    }

    function setShouldRevert(bool _revert) external {
        shouldRevert = _revert;
    }

    function masterCopy() external view returns (address) {
        if (shouldRevert) revert("Simulated Safe revert");
        return masterCopyAddress;
    }

    function getThreshold() external view returns (uint256) {
        if (shouldRevert) revert("Simulated Safe revert");
        return thresholdValue;
    }

    function getOwners() external view returns (address[] memory) {
        if (shouldRevert) revert("Simulated Safe revert");
        return ownersList;
    }

    function isModuleEnabled(address module) external view returns (bool) {
        if (shouldRevert) revert("Simulated Safe revert");
        for (uint256 i = 0; i < enabledModules.length; i++) {
            if (enabledModules[i] == module) return true;
        }
        return false;
    }

    function getModulesPaginated(address, uint256) external view returns (address[] memory array, address next) {
        if (shouldRevert) revert("Simulated Safe revert");
        return (enabledModules, SENTINEL_MODULES);
    }

    function getStorageAt(uint256 offset, uint256) external view returns (bytes memory) {
        if (shouldRevert) revert("Simulated Safe revert");
        if (bytes32(offset) == FALLBACK_HANDLER_STORAGE_SLOT) {
            return abi.encode(fallbackHandlerAddress);
        }
        if (bytes32(offset) == GUARD_STORAGE_SLOT) {
            return abi.encode(guardAddress);
        }
        return abi.encode(bytes32(0));
    }
}

contract SafeAccountVerifierTest is Test {
    address internal constant SAFE_SINGLETON = 0x41675C099F32341bf84BFc5382aF534df5C7461a;
    address internal constant SAFE7579 = 0x7579EE8307284F293B1927136486880611F20002;
    address internal guard = makeAddr("guard");
    address internal owner = makeAddr("owner");

    SafeAccountVerifier internal verifier;
    MockSafeAccount internal safe;

    function setUp() public {
        verifier = new SafeAccountVerifier(SAFE_SINGLETON, SAFE7579, guard);
        safe = new MockSafeAccount(SAFE_SINGLETON, owner, SAFE7579, guard);
    }

    function test_verify_genuine_safe_succeeds() public view {
        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertTrue(genuine);
        assertEq(verifiedOwner, owner);
    }

    function test_verify_eoa_or_empty_code_fails() public view {
        (bool genuine, address verifiedOwner) = verifier.verify(owner);
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));

        (bool genuineZero, address verifiedZero) = verifier.verify(address(0));
        assertFalse(genuineZero);
        assertEq(verifiedZero, address(0));
    }

    function test_verify_wrong_singleton_fails() public {
        safe.setMasterCopy(makeAddr("wrongSingleton"));
        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_threshold_not_one_fails() public {
        safe.setThreshold(2);
        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_multiple_owners_fails() public {
        address[] memory multiple = new address[](2);
        multiple[0] = owner;
        multiple[1] = makeAddr("owner2");
        safe.setOwners(multiple);

        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_owner_is_contract_fails() public {
        address contractOwner = address(new MockSafeAccount(SAFE_SINGLETON, owner, SAFE7579, guard));
        address[] memory singleContract = new address[](1);
        singleContract[0] = contractOwner;
        safe.setOwners(singleContract);

        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_wrong_fallback_handler_fails() public {
        safe.setFallbackHandler(makeAddr("wrongHandler"));
        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_extra_module_fails_closed() public {
        address[] memory multipleModules = new address[](2);
        multipleModules[0] = SAFE7579;
        multipleModules[1] = makeAddr("rogueModule");
        safe.setModules(multipleModules);

        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_safe7579_not_enabled_fails() public {
        address[] memory emptyModules = new address[](0);
        safe.setModules(emptyModules);

        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_wrong_guard_fails() public {
        safe.setGuard(makeAddr("wrongGuard"));
        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }

    function test_verify_reverting_safe_fails_closed() public {
        safe.setShouldRevert(true);
        (bool genuine, address verifiedOwner) = verifier.verify(address(safe));
        assertFalse(genuine);
        assertEq(verifiedOwner, address(0));
    }
}
