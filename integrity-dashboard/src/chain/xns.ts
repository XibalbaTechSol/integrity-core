// Minimal ABI for XibalbaNameService (contracts/src/framework/XibalbaNameService.sol) —
// only the functions the dashboard's write flow calls, same "only what we call" spirit as
// chain/markets.ts's ABIs.
export const XNS_ABI = [
  'function register(string handle) returns (bytes32 id)',
  'function setPrimaryHandle(string handle)',
  'function release(string handle)',
] as const;
