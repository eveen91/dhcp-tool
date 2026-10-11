import { expect, test } from '@playwright/test';

test('browser reaches the real Django API through the frontend proxy', async ({ page }) => {
  const responsePromise = page.waitForResponse(
    (response) => new URL(response.url()).pathname === '/api/v1/health/',
  );
  await page.goto('/');
  const response = await responsePromise;
  expect(response.status()).toBe(200);
  expect(await response.json()).toEqual({ status: 'ok' });
  expect(response.headers()['cache-control']).toBe('no-store');
  await expect(page.getByRole('status')).toHaveText('API dostępne');
});

test('browser reports API failure', async ({ page }) => {
  // This case verifies UI failure handling; the success case above uses the live API.
  await page.route('**/api/v1/health/', (route) => route.abort());
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('API niedostępne');
});
