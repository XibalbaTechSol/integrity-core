import { Page } from '@playwright/test';

/** Collects uncaught page errors (real JS crashes) for a page, for assertion in specs.
 *  Deliberately NOT console.error messages — those include noisy third-party/dev-mode
 *  warnings unrelated to correctness; a real crash surfaces via 'pageerror'. */
export function collectPageErrors(page: Page): Error[] {
  const errors: Error[] = [];
  page.on('pageerror', (err) => errors.push(err));
  return errors;
}
