import { graphMemory } from './graphMemory';
import { shieldBackend } from './shieldBackend';
import { oracle } from './oracle';
import { XIBALBA_TEST_AGENT_ID } from '../constants';

// Cross-system fan-out for the Guided System Test wizard (~/.claude/plans/
// velvet-giggling-quill.md). Dashboard-orchestrated, not backend-to-backend webhooks --
// see the plan's Context section for why: the dashboard already talks to all three
// systems, so it makes three parallel writes (one to each system's own generic event
// log) instead of relying on the systems to notify each other. Every write is tagged
// with the same real, on-chain registered identity so a test run is queryable by the
// same id from any of the three.
//
// Promise.allSettled, not Promise.all/await-each: one system being down (or its log
// write failing) must never look like the TEST itself failed -- the caller already
// knows the test's own pass/fail before calling this. This function's own return value
// reports fan-out delivery, not test correctness.

export const XIBALBA_SYSTEM_TESTS_SESSION_ID = 'xibalba-system-tests';

export interface TestResultReport {
  testName: string;
  status: 'passed' | 'failed';
  detail?: string;
  metadata?: Record<string, unknown>;
}

export interface FanOutOutcome {
  cortex: 'ok' | 'failed';
  shield: 'ok' | 'failed';
  oracle: 'ok' | 'failed';
}

export async function reportTestResult(report: TestResultReport): Promise<FanOutOutcome> {
  const { testName, status, detail, metadata } = report;

  const results = await Promise.allSettled([
    graphMemory.recordOtelBatch(XIBALBA_SYSTEM_TESTS_SESSION_ID, [
      {
        kind: 'log',
        name: 'guided_system_test',
        attributes: { test_name: testName, status, detail, agent_id: XIBALBA_TEST_AGENT_ID, ...metadata },
      },
    ]),
    shieldBackend.recordTestEvent({
      agent_id: XIBALBA_TEST_AGENT_ID,
      test_name: testName,
      status,
      detail,
      metadata,
    }),
    oracle.ingestAudit({
      agent_id: XIBALBA_TEST_AGENT_ID,
      source: 'dashboard',
      event_type: 'guided_system_test',
      decision: status === 'passed' ? 'allow' : 'deny',
      detail: detail ?? testName,
      metadata: { test_name: testName, ...metadata },
    }),
  ]);

  const [cortexResult, shieldResult, oracleResult] = results;
  return {
    cortex: cortexResult.status === 'fulfilled' ? 'ok' : 'failed',
    shield: shieldResult.status === 'fulfilled' ? 'ok' : 'failed',
    oracle: oracleResult.status === 'fulfilled' ? 'ok' : 'failed',
  };
}
