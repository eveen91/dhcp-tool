import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { HealthStatus } from './health-status';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test('shows connected status after the health endpoint responds ok', async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ status: 'ok' }),
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<HealthStatus />);

  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('API dostępne'));
  expect(fetchMock).toHaveBeenCalledWith(
    '/api/v1/health/',
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});

test('shows unavailable status when the health endpoint fails', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network error')));

  render(<HealthStatus />);

  await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('API niedostępne'));
});
