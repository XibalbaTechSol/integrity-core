// SPDX-License-Identifier: MIT
pragma solidity ^0.8.28;

import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {XibalbaAgentRegistry} from "../framework/XibalbaAgentRegistry.sol";
import {IntegrityMarket} from "./IntegrityMarket.sol";

/// @title MarketFactory
/// @notice Lets any registered agent deploy and OWN its own customized `IntegrityMarket`
/// instance -- the application-layer expression of the protocol's core thesis. Agents
/// don't just self-deploy their identity primitives (SovereignAgent, StateAnchor) and
/// own clones of shared infrastructure (ReputationRegistry, Slasher, ...); they can also
/// author and own the smart-contract *applications* built on top of the protocol.
/// integrity-dashboard's Contracts/Factory IDE page is the human-facing surface for this
/// exact call -- pick a question, outcome structure, AIS bar, deadline, and resolver,
/// then deploy for real. No two agents' markets need to look alike: one might gate entry
/// at AIS 900 with itself as resolver, another might open entry to any registered agent
/// and delegate resolution to the protocol's demo signer.
/// @dev Mirrors AgentPrimitivesFactory's clone-and-initialize pattern exactly (Clones of
/// one shared, non-initializable implementation), but for an application contract
/// instead of an identity primitive. Deliberately NOT restricted to a curator role --
/// unlike SmartBAAFactory (where "who can create a BAA" is gated by the Integrity Health vertical's
/// entity-registry check), any agent that completed real self-sovereign registration
/// (i.e. exists in XibalbaAgentRegistry) may deploy a market. Spam/quality is a
/// dashboard/discovery-layer concern (e.g. surfacing markets by creator AIS), not an
/// on-chain gate -- gating market *creation* itself would undercut the "agents own their
/// own applications" thesis this contract exists to demonstrate.
contract MarketFactory {
    XibalbaAgentRegistry public immutable agentRegistry;

    /// @dev The shared, non-initializable IntegrityMarket implementation every clone
    /// delegatecalls into (deployed once by script/Deploy.s.sol with
    /// `_disableInitializers()` already called in its constructor).
    address public immutable marketImpl;

    mapping(address => address[]) public marketsByCreator;
    address[] public allMarkets;

    event MarketDeployed(
        address indexed market, address indexed creator, string question, uint8 outcomeCount, address indexed resolver
    );

    error AgentNotRegistered();

    constructor(address _agentRegistry, address _marketImpl) {
        agentRegistry = XibalbaAgentRegistry(_agentRegistry);
        marketImpl = _marketImpl;
    }

    /// @notice Deploys and initializes a new `IntegrityMarket` clone owned by
    /// `msg.sender` (expected to be the calling agent's own SovereignAgent contract,
    /// per the protocol's call-routing convention -- `agentRegistry.isRegisteredAgent`
    /// is exactly the check that closes off a hand-rolled non-agent caller, same as
    /// EHRGate/IntegrityMarket's own resolution pattern).
    function deployMarket(
        string calldata question,
        uint8 outcomeCount,
        uint256 minAisToEnter,
        uint256 resolveDeadline,
        address resolver
    ) external returns (address market) {
        if (!agentRegistry.isRegisteredAgent(msg.sender)) revert AgentNotRegistered();

        market = Clones.clone(marketImpl);
        IntegrityMarket(market).initialize(msg.sender, question, outcomeCount, minAisToEnter, resolveDeadline, resolver);

        marketsByCreator[msg.sender].push(market);
        allMarkets.push(market);

        emit MarketDeployed(market, msg.sender, question, outcomeCount, resolver);
    }

    function getMarketsByCreator(address creator) external view returns (address[] memory) {
        return marketsByCreator[creator];
    }

    function allMarketsCount() external view returns (uint256) {
        return allMarkets.length;
    }
}
