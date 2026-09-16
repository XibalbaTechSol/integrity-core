import { test, expect } from '@playwright/test';
import { ethers } from 'ethers';
import { canWrite, type PermissionContext } from '../src/integrity/permissions';
import { simulateAgentExecution } from '../src/integrity/wallet/simulation';

const CONTROLLER = '0x1111111111111111111111111111111111111111';
const OTHER_SIGNER = '0x2222222222222222222222222222222222222222';

function fixture(overrides: Partial<PermissionContext> = {}): PermissionContext {
  return {
    chainId: 84532,
    expectedChainId: 84532,
    signerAddress: CONTROLLER,
    verifiedController: CONTROLLER,
    requiredRoleConfirmed: true,
    simulationPassed: true,
    stateFresh: true,
    ...overrides,
  };
}

test.describe('write safety gates', () => {
  test('allows a write only when every independent gate is satisfied', () => {
    expect(canWrite(fixture())).toBe(true);

    const blockingCases: Partial<PermissionContext>[] = [
      { chainId: 1 },
      { signerAddress: null },
      { signerAddress: OTHER_SIGNER },
      { verifiedController: null },
      { requiredRoleConfirmed: false },
      { simulationPassed: false },
      { stateFresh: false },
    ];

    for (const blocked of blockingCases) {
      expect(canWrite(fixture(blocked)), JSON.stringify(blocked)).toBe(false);
    }
  });

  test('headless wallet flow fails closed before a transfer form or write', async ({ page }) => {
    const writeRequests: string[] = [];
    page.on('request', (request) => {
      if (request.method() !== 'GET' && /send|transfer|approve|transaction|eth_sendTransaction/i.test(request.url())) {
        writeRequests.push(`${request.method()} ${request.url()}`);
      }
    });

    await page.goto('/financials');
    await page.getByRole('button', { name: 'Send' }).click();
    await expect(page.getByRole('heading', { name: 'Connect a wallet first' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Connect Wallet' })).toBeVisible();
    expect(writeRequests).toEqual([]);
  });

  test('simulates the exact SovereignAgent envelope without exposing a send path', async () => {
    const calls: ethers.TransactionRequest[] = [];
    const executeInterface = new ethers.Interface(['function execute(address target,uint256 value,bytes data)']);
    const simulator = {
      async call(transaction: ethers.TransactionRequest) {
        if (transaction.from?.toLowerCase() !== CONTROLLER.toLowerCase()) {
          throw new Error('NotController');
        }
        calls.push(transaction);
        return '0x';
      },
    };
    const agent = '0x3333333333333333333333333333333333333333';
    const target = '0x4444444444444444444444444444444444444444';
    const payload = new ethers.Interface(['function transfer(address to,uint256 amount)'])
      .encodeFunctionData('transfer', [OTHER_SIGNER, ethers.parseEther('1')]);
    const executeData = executeInterface.encodeFunctionData('execute', [target, 0n, payload]);
    await simulateAgentExecution(simulator, CONTROLLER, agent, target, payload);

    expect(calls).toEqual([{ to: agent, from: CONTROLLER, data: executeData, value: 0n }]);
    await expect(simulateAgentExecution(simulator, OTHER_SIGNER, agent, target, payload)).rejects.toThrow('NotController');
    expect(calls).toHaveLength(1);
    const [decodedTarget, decodedValue, decodedPayload] = executeInterface.decodeFunctionData('execute', executeData);
    expect(decodedTarget).toBe(target);
    expect(decodedValue).toBe(0n);
    expect(decodedPayload).toBe(payload);
    expect('send' in simulator).toBe(false);
    expect('sendTransaction' in simulator).toBe(false);
  });
});
