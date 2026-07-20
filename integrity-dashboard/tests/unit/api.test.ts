import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { api } from '../../src/services/api';
import { API_BASE } from '../../src/constants';

vi.mock('axios');

describe('ApiService', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAgents', () => {
    it('fetches agents successfully', async () => {
      const mockData = [{ id: '1', name: 'Agent 1' }];
      (axios.get as any).mockResolvedValue({ data: mockData });

      const result = await api.getAgents();

      expect(axios.get).toHaveBeenCalledWith(`${API_BASE}/v1/user/agents`, {
        headers: { Authorization: 'Bearer master_agent_token' }
      });
      expect(result).toEqual(mockData);
    });
  });

  describe('updateAgentMetadata', () => {
    it('updates agent metadata successfully', async () => {
      const mockData = { status: 'success' };
      (axios.patch as any).mockResolvedValue({ data: mockData });

      const result = await api.updateAgentMetadata('0x123', { test: true });

      expect(axios.patch).toHaveBeenCalledWith(`${API_BASE}/v1/agent/0x123/metadata`, { test: true }, {
        headers: { Authorization: 'Bearer master_agent_token' }
      });
      expect(result).toEqual(mockData);
    });
  });

  describe('subscribeToMetrics', () => {
    it('subscribes to SSE successfully and handles messages', () => {
      let mockEventSource = {
        onmessage: null as any,
        onerror: null as any,
        close: vi.fn(),
      };
      const eventSourceSpy = vi.fn();
      class MockEventSource {
        onmessage: any = null;
        onerror: any = null;
        close = vi.fn();
        constructor(url: string) {
          eventSourceSpy(url);
          mockEventSource = this as any;
        }
      }
      (global as any).EventSource = MockEventSource;
      
      const callback = vi.fn();
      const unsubscribe = api.subscribeToMetrics(callback);
      
      expect(eventSourceSpy).toHaveBeenCalledWith(`${API_BASE}/v1/metrics/stream`);
      
      // simulate message
      if (mockEventSource.onmessage) {
        mockEventSource.onmessage({ data: JSON.stringify({ key: 'value' }) });
      }
      expect(callback).toHaveBeenCalledWith({ key: 'value' });
      
      // simulate error message parsing
      const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
      if (mockEventSource.onmessage) {
        mockEventSource.onmessage({ data: 'invalid json' });
      }
      expect(consoleErrorSpy).toHaveBeenCalled();
      
      // simulate error
      if (mockEventSource.onerror) {
        mockEventSource.onerror(new Error('SSE Error'));
      }
      expect(consoleErrorSpy).toHaveBeenCalledWith('SSE Error', expect.any(Error));

      consoleErrorSpy.mockRestore();
      
      // simulate unsubscribe
      unsubscribe();
      expect(mockEventSource.close).toHaveBeenCalled();
    });
  });

  describe('generic fetch and post calls', () => {
    it('calls generic fetch methods', async () => {
      const mockData = { success: true };
      (axios.get as any).mockResolvedValue({ data: mockData });
      
      await api.getAgentIdentity('0x1');
      await api.getApiKeys();
      await api.getProtocolStats();
      await api.getAgentContracts('0x1');
      await api.getAllContracts();
      await api.getCreditProfile('0x1');
      await api.getReputationHistory('0x1');
      await api.getProposals();
      await api.getMarketTasks();
      await api.getProvenance('0x1');
      await api.getBenchmarks();
      await api.getWalletBalance('0x1');
      await api.getBAAs();
      await api.getShieldInteractions();
      await api.getComplianceReviewQueue();
      
      expect(axios.get).toHaveBeenCalled();
    });

    it('calls generic post methods', async () => {
      const mockData = { success: true };
      (axios.post as any).mockResolvedValue({ data: mockData });
      
      await api.registerAgent({} as any);
      await api.generateClaimChallenge('0x1', '0x2');
      await api.claimOwnership('0x1', {});
      await api.generateApiKey(30);
      await api.deleteApiKey('key');
      await api.claimContract('0x1', {} as any);
      await api.deployContract({} as any);
      await api.listMarketContract({} as any);
      await api.borrow('0x1', {} as any);
      await api.repay('0x1', {} as any);
      await api.fundTaskWithLoan({} as any);
      await api.generateZKProof('0x1', {});
      await api.createProposal({} as any);
      await api.voteProposal('1', 'for');
      await api.stake('0x1', 100);
      await api.createMarketTask({} as any);
      await api.bidOnTask({} as any);
      await api.settleAuction('task');
      await api.requestAudit('0x1', 'type');
      await api.transferTokens('0x1', '0x2', 10);
      await api.proposeBAA({});
      await api.signBAA('baa', 'sig');
      await api.resolveComplianceViolation('id', 'dismiss');
      await api.reportTelemetry({} as any);
      await api.disputeTransaction('deal', 'init', 'reason');
      
      expect(axios.post).toHaveBeenCalled();
    });
  });
});
