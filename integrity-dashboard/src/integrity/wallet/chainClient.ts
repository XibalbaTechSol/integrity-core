import { ethers } from 'ethers';
import { BASE_SEPOLIA_CHAIN_ID, ITK_TOKEN_ADDRESS, RPC_URL } from '../../constants';
import { IntegrityError } from '../errors';

const ERC20_READ_ABI = [
  'function balanceOf(address owner) view returns (uint256)',
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
] as const;

export interface OnChainBalance {
  address: string;
  eth: string;
  itk: string;
  itkSymbol: string;
  decimals: number;
  chainId: number;
  blockNumber: number;
}

export async function readAgentBalances(address: string): Promise<OnChainBalance> {
  if (!ethers.isAddress(address)) throw new IntegrityError('The resolved agent wallet is not a valid EVM address.', { source: 'local' });
  const provider = new ethers.JsonRpcProvider(RPC_URL, BASE_SEPOLIA_CHAIN_ID, { staticNetwork: true });
  try {
    const [network, blockNumber, eth, token] = await Promise.all([
      provider.getNetwork(), provider.getBlockNumber(), provider.getBalance(address),
      Promise.resolve(new ethers.Contract(ITK_TOKEN_ADDRESS, ERC20_READ_ABI, provider)),
    ]);
    const [itk, decimals, symbol] = await Promise.all([
      token.balanceOf(address) as Promise<bigint>,
      token.decimals() as Promise<number>,
      token.symbol() as Promise<string>,
    ]);
    const chainId = Number(network.chainId);
    if (chainId !== BASE_SEPOLIA_CHAIN_ID) throw new IntegrityError(`RPC returned chain ${chainId}, expected ${BASE_SEPOLIA_CHAIN_ID}.`, { source: 'rpc' });
    return { address, eth: ethers.formatEther(eth), itk: ethers.formatUnits(itk, decimals), itkSymbol: symbol, decimals, chainId, blockNumber };
  } catch (error) {
    if (error instanceof IntegrityError) throw error;
    throw new IntegrityError('On-chain balance read failed.', { source: 'rpc', retryable: true });
  }
}

export function getBrowserProvider(): ethers.BrowserProvider | null {
  const ethereum = (globalThis as { ethereum?: ethers.Eip1193Provider }).ethereum;
  return ethereum ? new ethers.BrowserProvider(ethereum) : null;
}
