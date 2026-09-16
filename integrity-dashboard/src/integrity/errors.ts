export type IntegrityErrorSource = 'local' | 'api' | 'wallet' | 'rpc' | 'chain' | 'indexer' | 'verification' | 'unknown';

export class IntegrityError extends Error {
  readonly source: IntegrityErrorSource;
  readonly retryable: boolean;
  readonly status?: number;

  constructor(message: string, options: { source?: IntegrityErrorSource; retryable?: boolean; status?: number } = {}) {
    super(message);
    this.name = 'IntegrityError';
    this.source = options.source ?? 'unknown';
    this.retryable = options.retryable ?? false;
    this.status = options.status;
  }
}

export function normalizeIntegrityError(error: unknown, source: IntegrityErrorSource = 'unknown'): IntegrityError {
  if (error instanceof IntegrityError) return error;
  if (error instanceof Error) return new IntegrityError(error.message, { source });
  return new IntegrityError('The operation failed without a diagnostic.', { source });
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}
