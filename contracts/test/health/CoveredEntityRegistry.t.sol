// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Test} from "forge-std/Test.sol";
import {CoveredEntityRegistry} from "../../src/health/CoveredEntityRegistry.sol";

contract CoveredEntityRegistryTest is Test {
    CoveredEntityRegistry registry;
    address admin = makeAddr("admin");
    address hospital = makeAddr("hospital");
    address aiVendor = makeAddr("aiVendor");

    function setUp() public {
        registry = new CoveredEntityRegistry(admin);
    }

    function test_registerCoveredEntity() public {
        vm.prank(admin);
        registry.registerEntity(hospital, CoveredEntityRegistry.EntityType.CoveredEntity, "ipfs://hospital-profile");

        assertTrue(registry.isActiveCoveredEntity(hospital));
        assertFalse(registry.isActiveBusinessAssociate(hospital));
    }

    function test_registerBusinessAssociate() public {
        vm.prank(admin);
        registry.registerEntity(aiVendor, CoveredEntityRegistry.EntityType.BusinessAssociate, "ipfs://vendor-profile");

        assertTrue(registry.isActiveBusinessAssociate(aiVendor));
        assertFalse(registry.isActiveCoveredEntity(aiVendor));
    }

    function test_revokeDeactivates() public {
        vm.startPrank(admin);
        registry.registerEntity(hospital, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");
        registry.revokeEntity(hospital);
        vm.stopPrank();

        assertFalse(registry.isActiveCoveredEntity(hospital));
    }

    function test_onlyRegistrarCanRegister() public {
        vm.expectRevert();
        registry.registerEntity(hospital, CoveredEntityRegistry.EntityType.CoveredEntity, "uri");
    }

    function test_cannotRegisterUnregisteredType() public {
        vm.prank(admin);
        vm.expectRevert(CoveredEntityRegistry.UnknownEntityType.selector);
        registry.registerEntity(hospital, CoveredEntityRegistry.EntityType.Unregistered, "uri");
    }
}
