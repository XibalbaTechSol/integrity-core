// Small retry helper for read-only chain calls against a public, load-balanced RPC --
// this repo's own PRODUCTION_GAPS.md documents that Base Sepolia's public RPC nodes can
// briefly disagree with each other (the same root cause integrity_sdk/chain.py's
// `_send_signed`/`_call_with_retry` already work around for writes and reads on the
// Python side). A single transient "missing revert data"/CALL_EXCEPTION on an otherwise
// well-formed read shouldn't force a user to click a manual retry button themselves.
export async function withRetry<T>(fn: () => Promise<T>, attempts = 3, delayMs = 800): Promise<T> {
  let lastError: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await fn();
    } catch (e) {
      lastError = e;
      if (i < attempts - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs));
      }
    }
  }
  throw lastError;
}
