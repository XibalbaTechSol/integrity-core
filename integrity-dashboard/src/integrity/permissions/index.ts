import { ethers } from 'ethers';

export interface PermissionContext {
  chainId: number | null;
  expectedChainId: number;
  signerAddress: string | null;
  verifiedController: string | null;
  requiredRoleConfirmed: boolean;
  simulationPassed: boolean;
  stateFresh: boolean;
}

export function canWrite(context: PermissionContext): boolean {
  if (context.chainId !== context.expectedChainId || !context.signerAddress || !context.verifiedController) return false;
  if (!ethers.isAddress(context.signerAddress) || !ethers.isAddress(context.verifiedController)) return false;
  return context.signerAddress.toLowerCase() === context.verifiedController.toLowerCase()
    && context.requiredRoleConfirmed && context.simulationPassed && context.stateFresh;
}
