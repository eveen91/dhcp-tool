import { execFileSync } from 'node:child_process';
import { randomBytes, randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';

const username = `e2e-${randomUUID()}`;
const password = randomBytes(24).toString('base64url');

function account(action: 'create' | 'delete') {
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
      '../backend/tests/e2e_account.py',
      action,
    ],
    {
      env: {
        ...process.env,
        DJANGO_SETTINGS_MODULE: 'config.settings.test',
        DHCP_TOOL_E2E_USERNAME: username,
        DHCP_TOOL_E2E_PASSWORD: password,
      },
      stdio: 'pipe',
    },
  );
}

test.beforeAll(() => account('create'));
test.afterAll(() => account('delete'));

test('browser login and logout use CSRF and HttpOnly sessions through the real proxy', async ({
  page,
}) => {
  await page.goto('/');
  const result = await page.evaluate(
    async (credentials) => {
      const initial = await (await fetch('/api/v1/auth/session/')).json();
      const denied = await fetch('/api/v1/auth/session/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });
      const login = await fetch('/api/v1/auth/session/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': initial.csrf_token },
        body: JSON.stringify(credentials),
      });
      const loggedIn = await login.json();
      const current = await (await fetch('/api/v1/auth/session/')).json();
      const cookieVisible = document.cookie.includes('sessionid');
      const logout = await fetch('/api/v1/auth/session/', {
        method: 'DELETE',
        headers: { 'X-CSRFToken': loggedIn.csrf_token },
      });
      const final = await (await fetch('/api/v1/auth/session/')).json();
      return {
        denied: denied.status,
        login: login.status,
        user: current.user?.username,
        role: current.user?.role,
        cookieVisible,
        logout: logout.status,
        finalUser: final.user,
      };
    },
    { username, password },
  );
  expect(result).toEqual({
    denied: 403,
    login: 200,
    user: username,
    role: 'reader',
    cookieVisible: false,
    logout: 204,
    finalUser: null,
  });
});
