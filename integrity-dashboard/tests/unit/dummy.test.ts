import { describe, it, expect, vi } from 'vitest';
import { IS_PRODUCTION } from '../../src/constants';

vi.mock('../../src/constants', async () => {
  const actual = await vi.importActual('../../src/constants');
  return {
    ...actual as any,
    IS_PRODUCTION: true,
  };
});

describe('dummy', () => {
  it('works', () => {
    expect(IS_PRODUCTION).toBe(true);
  });
});
