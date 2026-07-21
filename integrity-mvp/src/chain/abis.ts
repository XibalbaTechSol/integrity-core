import type { Abi } from 'viem';
import SovereignAgent from '../abis/SovereignAgent.json';
import IntegrityMarket from '../abis/IntegrityMarket.json';
import IntegrityToken from '../abis/IntegrityToken.json';
import SmartBAA from '../abis/SmartBAA.json';
import XibalbaAgentRegistry from '../abis/XibalbaAgentRegistry.json';
import XibalbaNameService from '../abis/XibalbaNameService.json';
import AgentPrimitivesFactory from '../abis/AgentPrimitivesFactory.json';

// The synced JSON files are plain arrays (TS infers `type: string`, not the
// literal union viem's `Abi` type needs) — cast once here so every consumer
// gets a properly-typed ABI without repeating `as Abi` at every call site.
export const abis = {
    SovereignAgent: SovereignAgent as Abi,
    IntegrityMarket: IntegrityMarket as Abi,
    IntegrityToken: IntegrityToken as Abi,
    SmartBAA: SmartBAA as Abi,
    XibalbaAgentRegistry: XibalbaAgentRegistry as Abi,
    XibalbaNameService: XibalbaNameService as Abi,
    AgentPrimitivesFactory: AgentPrimitivesFactory as Abi,
} as const;
