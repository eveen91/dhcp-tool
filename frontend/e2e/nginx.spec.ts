import { execFileSync } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';
const suffix = randomUUID().slice(0, 8);
const username = `e2e-workspace-${suffix}`;
const password = randomBytes(24).toString('base64url');
const prefix = `e2e-nginx-${suffix}`;
const origin = 'http://127.0.0.1:3102';
function fixture(action: 'create' | 'delete') {
  execFileSync(
    'uv',
    [
      'run',
      '--project',
      '../backend',
      '--offline',
      '--no-sync',
      '--env-file',
      '../backend/.env.test',
      'python',
      '../backend/tests/e2e_workspace.py',
      action,
    ],
    {
      env: {
        ...process.env,
        DJANGO_SETTINGS_MODULE: 'config.settings.test',
        DHCP_TOOL_E2E_USERNAME: username,
        DHCP_TOOL_E2E_PASSWORD: password,
        DHCP_TOOL_E2E_PREFIX: prefix,
      },
      stdio: 'pipe',
    },
  );
}
test.beforeAll(() => fixture('create'));
test.afterAll(() => fixture('delete'));
test('Nginx and Next.js isolate private responses and serve safe uncached failures', async ({
  browser,
  page,
}) => {
  await page.goto(origin);
  await page.getByLabel('Nazwa użytkownika', { exact: false }).fill(username);
  await page.getByLabel('Hasło', { exact: false }).fill(password);
  await page.getByRole('button', { name: 'Zaloguj', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Lista firewalli' })).toBeVisible();
  const result = await page.evaluate(
    async ({ name }) => {
      const session = await (await fetch('/api/v1/auth/session/')).json();
      const headers = { 'Content-Type': 'application/json', 'X-CSRFToken': session.csrf_token };
      const created = await fetch('/api/v1/firewalls/', {
        method: 'POST',
        headers,
        body: JSON.stringify({ name, profile: 'R81.10' }),
      });
      const firewall = await created.json();
      const path = `/api/v1/firewalls/${firewall.id}/draft/`;
      const initial = await (await fetch(path)).json();
      const updated = await fetch(path, {
        method: 'PATCH',
        headers: { ...headers, 'X-Config-Revision': String(initial.revision) },
        body: JSON.stringify({ domain: 'private-one.test' }),
      });
      if (!updated.ok) throw new Error('Draft write failed');
      const first = await fetch(path, { cache: 'force-cache' });
      const data = await first.json();
      await fetch(path, {
        method: 'PATCH',
        headers: { ...headers, 'X-Config-Revision': String(data.revision) },
        body: JSON.stringify({ domain: 'private-two.test' }),
      });
      const next = await fetch(path, { cache: 'force-cache' });
      return {
        path,
        first: data.settings.domain,
        next: (await next.json()).settings.domain,
        cache: first.headers.get('Cache-Control'),
        vary: first.headers.get('Vary'),
      };
    },
    { name: prefix },
  );
  expect(result.first).toBe('private-one.test');
  expect(result.next).toBe('private-two.test');
  expect(result.cache).toContain('no-store');
  expect(result.vary).toContain('Cookie');
  const directNext = await page.request.get('http://127.0.0.1:3101' + result.path);
  expect(directNext.status()).toBe(200);
  expect(directNext.headers()['cache-control']).toContain('no-store');
  expect((await directNext.json()).settings.domain).toBe('private-two.test');
  const anonymous = await browser.newContext();
  try {
    const denied = await anonymous.request.get(origin + result.path);
    expect(denied.status()).toBe(403);
    expect(denied.headers()['cache-control']).toContain('no-store');
    expect(await denied.text()).not.toContain('private-');
    const nextDenied = await anonymous.request.get('http://127.0.0.1:3101' + result.path);
    expect(nextDenied.status()).toBe(403);
    expect(nextDenied.headers()['cache-control']).toContain('no-store');
    expect(await nextDenied.text()).not.toContain('private-');
    const outage = await anonymous.request.get(origin + '/api/v1/test-upstream-outage/');
    expect(outage.status()).toBe(503);
    expect(outage.headers()['cache-control']).toContain('no-store');
    expect((await outage.json()).error.code).toBe('upstream_unavailable');
    expect(await outage.text()).not.toContain('nginx');
  } finally {
    await anonymous.close();
  }
  await page.getByRole('button', { name: 'Wyloguj', exact: true }).click();
  const denied = await page.request.get(origin + result.path);
  expect(denied.status()).toBe(403);
  expect(await denied.text()).not.toContain('private-');
  const logs = await readFile('/tmp/dhcp-tool-nginx-e2e-access.log', 'utf8');
  expect(
    logs
      .trim()
      .split('\n')
      .every((line) => /^(GET|POST|PATCH|DELETE|PUT|HEAD|OPTIONS) [0-9]{3} [0-9.]+$/.test(line)),
  ).toBe(true);
  for (const secret of [username, password, 'private-one.test', 'private-two.test'])
    expect(logs).not.toContain(secret);
});
