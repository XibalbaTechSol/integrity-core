// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

interface IHookCall {
    function preCheck(address msgSender, uint256 msgValue, bytes calldata msgData)
        external
        returns (bytes memory hookData);
    function postCheck(bytes calldata hookData) external;
}

interface IModuleCall {
    function onInstall(bytes calldata data) external;
    function onUninstall(bytes calldata data) external;
}

struct Execution {
    address target;
    uint256 value;
    bytes callData;
}

contract MockGovernedAccount {
    address public hook;
    mapping(uint256 => mapping(address => bool)) public installedModules;

    receive() external payable {}

    function setHook(address _hook) external {
        hook = _hook;
        installedModules[4][_hook] = true;
    }

    function installModule(uint256 moduleType, address module, bytes calldata initData) external payable {
        if (hook != address(0)) {
            IHookCall(hook).preCheck(msg.sender, msg.value, msg.data);
        }

        installedModules[moduleType][module] = true;
        if (moduleType == 4) {
            hook = module;
        }

        (bool ok, bytes memory ret) = module.call(abi.encodeWithSelector(IModuleCall.onInstall.selector, initData));
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }

        if (hook != address(0)) {
            IHookCall(hook).postCheck("");
        }
    }

    function uninstallModule(uint256 moduleType, address module, bytes calldata deInitData) external payable {
        if (hook != address(0)) {
            IHookCall(hook).preCheck(msg.sender, msg.value, msg.data);
        }

        installedModules[moduleType][module] = false;
        if (moduleType == 4 && hook == module) {
            hook = address(0);
        }

        (bool ok, bytes memory ret) = module.call(abi.encodeWithSelector(IModuleCall.onUninstall.selector, deInitData));
        if (!ok) {
            assembly {
                revert(add(ret, 0x20), mload(ret))
            }
        }

        if (hook != address(0)) {
            IHookCall(hook).postCheck("");
        }
    }

    function isModuleInstalled(uint256 moduleType, address module, bytes calldata /*context*/)
        external
        view
        returns (bool)
    {
        return installedModules[moduleType][module];
    }

    function execute(bytes32 mode, bytes calldata executionCalldata) external payable returns (bytes memory) {
        bytes memory hookData = "";
        if (hook != address(0)) {
            hookData = IHookCall(hook).preCheck(msg.sender, msg.value, msg.data);
        }

        bytes1 callType = bytes1(mode);
        if (callType == 0x00) {
            address target = address(bytes20(executionCalldata[:20]));
            uint256 val = uint256(bytes32(executionCalldata[20:52]));
            bytes memory data = executionCalldata[52:];
            (bool ok, bytes memory ret) = target.call{value: val}(data);
            if (!ok) {
                assembly {
                    revert(add(ret, 0x20), mload(ret))
                }
            }
        } else if (callType == 0x01) {
            Execution[] memory execs = abi.decode(executionCalldata, (Execution[]));
            for (uint256 i = 0; i < execs.length; i++) {
                (bool ok, bytes memory ret) = execs[i].target.call{value: execs[i].value}(execs[i].callData);
                if (!ok) {
                    assembly {
                        revert(add(ret, 0x20), mload(ret))
                    }
                }
            }
        } else if (callType == 0xff) {
            address target = address(bytes20(executionCalldata[:20]));
            bytes memory data = executionCalldata[20:];
            (bool ok, bytes memory ret) = target.delegatecall(data);
            if (!ok) {
                assembly {
                    revert(add(ret, 0x20), mload(ret))
                }
            }
        }

        if (hook != address(0)) {
            IHookCall(hook).postCheck(hookData);
        }

        return "";
    }
}
