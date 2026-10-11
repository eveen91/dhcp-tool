import { afterEach, expect, it, vi } from 'vitest';
import { createApiClient, ApiError } from './workspace-client';

afterEach(() => vi.unstubAllGlobals());
it('uses the rotated session token and revision for writes without caching', async () => {
  const requests: RequestInit[] = [];
  vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
    requests.push(init);
    return new Response(
      JSON.stringify({ user: null, csrf_token: requests.length === 1 ? 'first' : 'rotated' }),
      { status: 200 },
    );
  });
  const api = createApiClient();
  await api.session();
  await api.login({ username: 'operator', password: 'password' });
  await api.request('/firewalls/id/draft/', {
    method: 'PATCH',
    body: { domain: 'example.test' },
    revision: 7,
  });
  expect(requests[1].headers).toMatchObject({ 'X-CSRFToken': 'first' });
  expect(requests[2].headers).toMatchObject({ 'X-CSRFToken': 'rotated', 'X-Config-Revision': '7' });
  expect(requests[2]).toMatchObject({ cache: 'no-store', credentials: 'same-origin' });
});
it('preserves field errors and current revision on conflict without retrying', async () => {
  let calls = 0;
  vi.stubGlobal('fetch', async () => {
    calls++;
    return new Response(
      JSON.stringify({
        error: { code: 'revision_conflict', message: 'Konflikt', fields: {}, current_revision: 9 },
      }),
      { status: 409 },
    );
  });
  const error = await createApiClient()
    .request('/firewalls/id/draft/', { method: 'PATCH', revision: 8, body: {} })
    .catch((e) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({ status: 409, currentRevision: 9 });
  expect(calls).toBe(1);
});
it('does not show HTML responses or raw network details to the user', async () => {
  vi.stubGlobal(
    'fetch',
    async () => new Response('<html>private upstream path</html>', { status: 502 }),
  );
  await expect(createApiClient().request('/firewalls/')).rejects.toThrow('Nie udało się');
});
