import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createApiClient } from '../lib/api/workspace-client';
import { AuditHistory } from './audit-history';
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('opens scoped before and after values with actor and correction reason', async () => {
  const event = {
    id: 'event',
    actor: 'admin',
    created_at: '2026-01-01T10:00:00Z',
    operation: 'deployment_correct',
    object_type: 'deployment',
    object_id: 'entry',
    request_id: 'req',
    revision: 1,
  };
  const fetcher = vi.fn(
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.endsWith('event/')
            ? {
                ...event,
                before: { status: 'successful' },
                after: { entry: { status: 'failed' }, correction_reason: 'Błędny wynik' },
              }
            : { count: 1, next: null, previous: null, results: [event] },
        ),
      ),
  );
  vi.stubGlobal('fetch', fetcher);
  render(<AuditHistory api={createApiClient()} firewallId="fw" />);
  fireEvent.click(await screen.findByRole('button', { name: /Pokaż zmianę/ }));
  expect(await screen.findByText(/Błędny wynik/)).toBeVisible();
  expect(screen.getByRole('heading', { name: 'Przed zmianą' })).toBeVisible();
  expect(fetcher).toHaveBeenCalledWith(
    '/api/v1/firewalls/fw/audit/event/',
    expect.objectContaining({ method: 'GET' }),
  );
});
