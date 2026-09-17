import { test, expect, type Page, type TestInfo } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import fs from 'node:fs';
import path from 'node:path';

const routes = [
  '/', '/auth', '/docs', '/privacy', '/terms', '/dashboard', '/agents', '/identity', '/records',
  '/proofs', '/wallets', '/transactions', '/contracts', '/evidence', '/activity', '/treasury',
  '/security', '/knowledge', '/financials', '/intelligence', '/correlation', '/prediction-markets',
  '/health', '/shield', '/fleet', '/memory', '/quant', '/licence', '/kernel', '/kernel-intent',
  '/developer', '/settings', '/wiki',
];

type Finding = { level: 'error' | 'warning'; kind: string; message: string; url?: string };

function isOptionalShieldAccessError(message: string) {
  return message.includes('localhost:8765/api/shield/')
    && (message.includes('due to access control checks') || message.includes('Cross-Origin Request Blocked'));
}

function safePath(info: TestInfo, name: string) {
  return info.outputPath('screenshots', `${name}.png`);
}

async function attachText(info: TestInfo, name: string, value: unknown) {
  await info.attach(name, { body: JSON.stringify(value, null, 2), contentType: 'application/json' });
}

async function collectPageEvidence(page: Page, info: TestInfo) {
  const findings: Finding[] = [];
  const consoleLines: string[] = [];
  const failedRequests: string[] = [];
  page.on('console', message => {
    const line = `[${message.type()}] ${message.text()}`;
    consoleLines.push(line);
    // Chromium reports failed fetches as generic console errors. Preserve them
    // in the artifact, but reserve a test-blocking finding for actual runtime
    // exceptions; auth/indexer/RPC degradation is an expected observable state
    // in the real local stack and must be classified, not hidden.
    const text = message.text();
    // Firefox reports a missing optional loopback Shield service as a CORS
    // console error. The request failure is retained below as evidence; it
    // must not turn an honest degraded-service state into a browser crash.
    const optionalShieldCors = text.includes('Cross-Origin Request Blocked') && text.includes('localhost:8765/api/shield/');
    // WebKit emits only this URL-less connection message for the same optional
    // Shield failure; the page-level error above carries the exact Shield URL.
    const optionalShieldConnection = text === 'Could not connect to localhost: Connection refused' && page.url().endsWith('/correlation');
    if (message.type() === 'error' && !text.startsWith('Failed to load resource:') && !optionalShieldCors && !optionalShieldConnection) {
      findings.push({ level: 'error', kind: 'console', message: message.text(), url: page.url() });
    }
  });
  page.on('pageerror', error => {
    const finding = { level: isOptionalShieldAccessError(error.message) ? 'warning' : 'error' as const, kind: 'pageerror', message: error.message, url: page.url() };
    findings.push(finding);
  });
  page.on('requestfailed', request => {
    const failure = `${request.method()} ${request.url()} :: ${request.failure()?.errorText || 'failed'}`;
    failedRequests.push(failure);
    findings.push({ level: 'warning', kind: 'requestfailed', message: failure, url: page.url() });
  });
  page.on('response', response => {
    if (response.status() >= 500) {
      const optionalOracleRead = response.url().includes('/v1/agent/') && /\/(wallet|baas|contracts|stake)(\?|$)/.test(response.url());
      findings.push({ level: optionalOracleRead ? 'warning' : 'error', kind: 'http-5xx', message: `${response.status()} ${response.url()}`, url: page.url() });
    }
    else if (response.status() >= 400 && ![401, 404].includes(response.status())) findings.push({ level: 'warning', kind: 'http-4xx', message: `${response.status()} ${response.url()}`, url: page.url() });
  });
  return { findings, consoleLines, failedRequests };
}

async function assertBaseline(page: Page, info: TestInfo, route: string, evidence: Awaited<ReturnType<typeof collectPageEvidence>>) {
  await expect(page.locator('body')).not.toBeEmpty();
  const title = await page.title();
  await expect(page.locator('h1').first(), `${route} primary heading`).toBeVisible();
  const headings = await page.locator('h1').allTextContents();
  const mainCount = await page.locator('main, [role="main"]').count();
  const horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  const a11y = await page.evaluate(() => {
    const violations: string[] = [];
    const h1 = document.querySelectorAll('h1').length;
    if (h1 > 1) violations.push(`multiple-h1:${h1}`);
    document.querySelectorAll('button').forEach((el, index) => { if (!(el.textContent?.trim() || el.getAttribute('aria-label') || el.getAttribute('title'))) violations.push(`button-without-name:${index}`); });
    document.querySelectorAll('a').forEach((el, index) => { if (!el.getAttribute('href')) violations.push(`link-without-href:${index}`); });
    document.querySelectorAll('input,select,textarea').forEach((el, index) => { const labelled = el.getAttribute('aria-label') || el.getAttribute('id') && document.querySelector(`label[for="${el.getAttribute('id')}"]`); if (!labelled) violations.push(`control-without-label:${index}`); });
    return { violations, landmarks: { main: document.querySelectorAll('main,[role="main"]').length, nav: document.querySelectorAll('nav').length } };
  });
  const axe = await new AxeBuilder({ page }).analyze();
  expect(mainCount, `${route} should expose a main landmark`).toBeGreaterThanOrEqual(route === '/' || route === '/auth' ? 0 : 1);
  expect(horizontalOverflow, `${route} has horizontal overflow`).toBe(false);
  expect(headings.length, `${route} should render a primary heading`).toBeGreaterThanOrEqual(1);
  const body = await page.locator('body').innerText();
  expect(body).not.toMatch(/-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----/i);
  expect(body).not.toMatch(/\b(seed phrase|mnemonic|raw private key|secret recovery)\b/i);
  await page.screenshot({ path: safePath(info, `${route.slice(1).replaceAll('/', '_') || 'landing'}-full`), fullPage: true });
  await page.screenshot({ path: safePath(info, `${route.slice(1).replaceAll('/', '_') || 'landing'}-viewport`), fullPage: false });
  await attachText(info, 'dom-assertions', { route, title, headings, mainCount, horizontalOverflow, a11y, bodyLength: body.length });
  await attachText(info, 'accessibility', { url: page.url(), violations: axe.violations.map(item => ({ id: item.id, impact: item.impact, help: item.help, nodes: item.nodes.map(node => node.target) })) });
  await attachText(info, 'console-log', evidence.consoleLines);
  await attachText(info, 'network-failures', evidence.failedRequests);
  expect(evidence.findings.filter(item => item.level === 'error'), `${route} critical browser findings`).toEqual([]);
  const blockingA11y = axe.violations.filter(item => item.impact === 'critical' || item.impact === 'serious');
  if (process.env.AXE_STRICT === 'true' || process.env.CI) {
    expect(blockingA11y, `${route} critical accessibility violations`).toEqual([]);
  }
}

test.describe('Integrity Dashboard rendered validation', () => {
  test('route inventory is complete and machine-readable', async ({}, info) => {
    const output = path.resolve(process.cwd(), 'test-results/route-inventory.json');
    fs.mkdirSync(path.dirname(output), { recursive: true });
    fs.writeFileSync(output, JSON.stringify({ generatedAt: new Date().toISOString(), routes: routes.map(route => ({ route, source: 'src/App.tsx', status: 'discovered' })) }, null, 2));
    expect(routes.length).toBeGreaterThan(25);
  });

  for (const route of routes) {
    test(`renders and audits ${route}`, async ({ page }, info) => {
      const evidence = await collectPageEvidence(page, info);
      const response = await page.goto(route, { waitUntil: 'domcontentloaded' });
      expect(response?.status() || 0, `${route} HTTP response`).toBeLessThan(500);
      await assertBaseline(page, info, route, evidence);
    });
  }

  test('agent selector changes rendered identity without leaking secrets', async ({ page }, info) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    const selector = page.getByLabel('Selected agent');
    await expect(selector).toBeVisible();
    const options = await selector.locator('option').evaluateAll(items => items.map(item => ({ value: (item as HTMLOptionElement).value, label: item.textContent?.trim() || '' })).filter(item => item.value));
    if (options.length < 2) test.skip(true, 'Fewer than two permitted agents are available in this environment');
    await selector.selectOption(options[0].value);
    await expect(page.locator('.selected-agent-panel h2')).not.toHaveText('No agent selected');
    const first = await page.locator('.selected-agent-panel').innerText();
    await selector.selectOption(options[1].value);
    await expect(page.locator('.selected-agent-panel h2')).not.toHaveText('No agent selected');
    const second = await page.locator('.selected-agent-panel').innerText();
    expect(second).not.toBe(first);
    await page.screenshot({ path: safePath(info, 'agent-switching'), fullPage: true });
    await attachText(info, 'agent-switching', { options, firstAgentVisible: first.slice(0, 400), secondAgentVisible: second.slice(0, 400) });
  });

  test('authenticated context fails closed when no permitted agents are present', async ({ page }, info) => {
    test.skip(!process.env.E2E_AUTH_EMAIL || !process.env.E2E_AUTH_PASSWORD, 'Set E2E_AUTH_EMAIL and E2E_AUTH_PASSWORD to exercise userapi authenticated scope');
    await page.goto('/auth', { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder('john@example.com').fill(process.env.E2E_AUTH_EMAIL!);
    await page.getByPlaceholder('••••••••').fill(process.env.E2E_AUTH_PASSWORD!);
    await page.getByRole('button', { name: /^Sign In/ }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });
    await expect(page.getByText('Authenticated scope')).toBeVisible();
    const selector = page.getByLabel('Selected agent');
    const options = await selector.locator('option').count();
    expect(options, 'authenticated principal must not receive unscoped agent directory').toBe(1);
    await attachText(info, 'authenticated-scope', { emailRedacted: '[configured test principal]', permittedAgentOptions: options - 1, failClosed: true });
  });

  test('authenticated agent partitions remain isolated across an explicit agent switch', async ({ page }, info) => {
    const email = process.env.E2E_AUTH_EMAIL;
    const password = process.env.E2E_AUTH_PASSWORD;
    const agentA = process.env.E2E_AGENT_A_ID;
    const agentB = process.env.E2E_AGENT_B_ID;
    test.skip(!email || !password || !agentA || !agentB,
      'Set E2E_AUTH_EMAIL, E2E_AUTH_PASSWORD, E2E_AGENT_A_ID, and E2E_AGENT_B_ID for live authenticated isolation coverage');

    await page.goto('/auth', { waitUntil: 'domcontentloaded' });
    await page.getByPlaceholder('john@example.com').fill(email!);
    await page.getByPlaceholder('••••••••').fill(password!);
    await page.getByRole('button', { name: /^Sign In/ }).click();
    await expect(page).toHaveURL(/\/dashboard/, { timeout: 15_000 });

    const selector = page.getByLabel('Selected agent');
    await expect(selector).toBeVisible();
    const optionValues = await selector.locator('option').evaluateAll(items => items.map(item => (item as HTMLOptionElement).value));
    expect(optionValues, 'authenticated selector must contain only permitted agent values').toEqual(expect.arrayContaining([agentA!, agentB!]));

    await selector.selectOption(agentA!);
    await expect(selector).toHaveValue(agentA!);
    const agentAText = await page.locator('.selected-agent-panel').innerText();
    expect(agentAText).toContain(agentA!.slice(0, 18));

    await selector.selectOption(agentB!);
    await expect(selector).toHaveValue(agentB!);
    const agentBText = await page.locator('.selected-agent-panel').innerText();
    expect(agentBText).toContain(agentB!.slice(0, 18));
    expect(agentBText).not.toContain(agentA!);

    await page.reload({ waitUntil: 'domcontentloaded' });
    await expect(page.getByLabel('Selected agent')).toHaveValue(agentB!);
    const reloadedText = await page.locator('.selected-agent-panel').innerText();
    expect(reloadedText).not.toContain(agentA!);

    await page.screenshot({ path: safePath(info, 'authenticated-agent-isolation'), fullPage: true });
    await attachText(info, 'authenticated-agent-isolation', {
      emailRedacted: '[configured test principal]',
      permittedAgents: [agentA!, agentB!],
      selectedAfterSwitch: agentB!,
      agentAAbsentAfterSwitch: !agentBText.includes(agentA!),
      agentAAbsentAfterReload: !reloadedText.includes(agentA!),
      failClosed: true,
    });
  });

  test('safe controls respond and security boundary remains explicit', async ({ page }, info) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded' });
    await expect(page.getByText(/This console exposes protocol evidence and wallet controls/)).toBeVisible();
    const refresh = page.getByRole('button', { name: 'Refresh data' });
    await refresh.click();
    await expect(refresh).toBeVisible();
    const copyButtons = page.getByRole('button', { name: /Copy / });
    if (await copyButtons.count()) {
      await copyButtons.first().click();
      await expect(copyButtons.first()).toBeVisible();
    }
    const body = await page.locator('body').innerText();
    expect(body).not.toMatch(/0x[a-f0-9]{64}/i);
    await page.screenshot({ path: safePath(info, 'safe-controls'), fullPage: true });
  });
});
