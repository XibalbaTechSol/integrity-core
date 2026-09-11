// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Script} from "forge-std/Script.sol";
import {console2} from "forge-std/console2.sol";
import {XibalbaAgentRegistry} from "../src/framework/XibalbaAgentRegistry.sol";
import {DomainRegistry} from "../src/framework/DomainRegistry.sol";

/// @title ReconcileFactoryRoles
/// @notice Repairs registrar-role drift after a factory rotation without deploying a
/// replacement. The signer must be an admin of both registries.
/// @dev Required env: REGISTRY_ADMIN_PRIVATE_KEY, CURRENT_FACTORY. Optional: OLD_FACTORY.
/// Run from contracts/ with `forge script script/ReconcileFactoryRoles.s.sol
/// --rpc-url base_sepolia --broadcast`.
contract ReconcileFactoryRoles is Script {
    function run() external {
        uint256 adminKey = vm.envUint("REGISTRY_ADMIN_PRIVATE_KEY");
        address currentFactory = vm.envAddress("CURRENT_FACTORY");
        address oldFactory = vm.envOr("OLD_FACTORY", address(0));
        string memory json = vm.readFile("../deployments.baseSepolia.json");
        address registry = vm.parseJsonAddress(json, ".singletons.XibalbaAgentRegistry");
        address domainRegistry = vm.parseJsonAddress(json, ".singletons.DomainRegistry");

        vm.startBroadcast(adminKey);
        XibalbaAgentRegistry(registry).grantRole(
            XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), currentFactory
        );
        DomainRegistry(domainRegistry).grantRole(
            DomainRegistry(domainRegistry).REGISTRAR_ROLE(), currentFactory
        );
        _assertReady(registry, domainRegistry, currentFactory);

        if (oldFactory != address(0) && oldFactory != currentFactory) {
            XibalbaAgentRegistry(registry).revokeRole(
                XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), oldFactory
            );
            DomainRegistry(domainRegistry).revokeRole(
                DomainRegistry(domainRegistry).REGISTRAR_ROLE(), oldFactory
            );
            require(
                !XibalbaAgentRegistry(registry).hasRole(
                    XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), oldFactory
                ),
                "old registry role remains"
            );
            require(
                !DomainRegistry(domainRegistry).hasRole(
                    DomainRegistry(domainRegistry).REGISTRAR_ROLE(), oldFactory
                ),
                "old domain role remains"
            );
        }
        vm.stopBroadcast();

        console2.log("Factory role reconciliation complete");
        console2.log("Registry:", registry);
        console2.log("DomainRegistry:", domainRegistry);
        console2.log("Current factory:", currentFactory);
    }

    function _assertReady(address registry, address domainRegistry, address factory) internal view {
        require(factory.code.length != 0, "current factory has no bytecode");
        require(
            XibalbaAgentRegistry(registry).hasRole(
                XibalbaAgentRegistry(registry).REGISTRAR_ROLE(), factory
            ),
            "current factory missing registry registrar role"
        );
        require(
            DomainRegistry(domainRegistry).hasRole(
                DomainRegistry(domainRegistry).REGISTRAR_ROLE(), factory
            ),
            "current factory missing domain registrar role"
        );
    }
}
