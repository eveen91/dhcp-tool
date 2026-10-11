import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createApiClient } from '../lib/api/workspace-client';
import { DeploymentLedger } from './deployment-ledger';
const entry = {
  id: 'entry',
  version_id: 'v1',
  version_number: 1,
  profile: 'R81.10',
  operator: 'operator',
  occurred_at: '2026-01-01T10:00:00Z',
  created_at: '2026-01-01T11:00:00Z',
  revision: 1,
  status: 'successful',
  confirmation: 'manual',
  note: '',
  ticket: 'INC-1',
  supplied_hash: '0'.repeat(64),
  artifact_sha256: 'a'.repeat(64),
  hash_comparison: 'mismatch',
};
function setup(role = 'operator', fail = false) {
  const fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    const data =
      init?.method === 'PATCH'
        ? fail
          ? {
              error: {
                code: 'deployment_conflict',
                message: 'Wpis został skorygowany.',
                current_revision: 2,
              },
            }
          : { ...entry, revision: 2, status: 'failed' }
        : url.includes('versions/')
          ? { count: 1, results: [{ id: 'v1', number: 1, description: 'Pierwsza' }] }
          : url.endsWith('latest/')
            ? { deployment: entry }
            : url.endsWith('entry/')
              ? entry
              : { count: 1, next: null, previous: null, results: [entry] };
    return new Response(JSON.stringify(data), {
      status: init?.method === 'PATCH' && fail ? 409 : 200,
    });
  });
  vi.stubGlobal('fetch', fetcher);
  const dirty = vi.fn();
  render(
    <DeploymentLedger
      api={createApiClient()}
      firewallId="fw"
      role={role}
      archived={false}
      onDirty={dirty}
      onBusyChange={vi.fn()}
      onChanged={vi.fn()}
    />,
  );
  return { fetcher, dirty };
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('shows manual hash mismatch and exposes no writes to a reader or editor', async () => {
  setup('reader');
  expect(await screen.findByText('INC-1')).toBeVisible();
  expect(screen.getAllByText(/Niezgodny/).length).toBeGreaterThan(0);
  expect(screen.getByText(/nie odczytuje firewalla/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Dodaj wpis' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Skoryguj/ })).not.toBeInTheDocument();
});
it('keeps correction input on conflict and never retries the write automatically', async () => {
  const { fetcher } = setup('operator', true);
  await screen.findByText('INC-1');
  fireEvent.click(screen.getByRole('button', { name: /Skoryguj wpis/ }));
  const reason = await screen.findByLabelText(/Uzasadnienie korekty/);
  fireEvent.change(reason, { target: { value: 'Poprawa wyniku' } });
  fireEvent.change(screen.getByLabelText(/Wynik/), { target: { value: 'failed' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz korektę' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Wpis został skorygowany');
  expect(reason).toHaveValue('Poprawa wyniku');
  expect(screen.getByLabelText(/Wynik/)).toHaveValue('failed');
  await waitFor(() =>
    expect(fetcher.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(1),
  );
  const call = fetcher.mock.calls.find(([, init]) => init?.method === 'PATCH')!;
  expect(JSON.parse(String(call[1]?.body))).toMatchObject({
    expected_revision: 1,
    correction_reason: 'Poprawa wyniku',
  });
});
it('cancelling a dirty form asks before discarding values', async () => {
  setup();
  await screen.findByText('INC-1');
  fireEvent.click(screen.getByRole('button', { name: 'Dodaj wpis' }));
  fireEvent.change(await screen.findByLabelText('Notatka'), { target: { value: 'Zachowaj mnie' } });
  fireEvent.click(screen.getByRole('button', { name: 'Anuluj formularz' }));
  expect(screen.getByRole('dialog')).toHaveTextContent('niezapisane');
  fireEvent.click(screen.getByRole('button', { name: /^Anuluj$/ }));
  expect(screen.getByLabelText('Notatka')).toHaveValue('Zachowaj mnie');
});
it('keeps the chosen artifact visible when browsing another page of versions', async () => {
  vi.stubGlobal(
    'fetch',
    async (url: string) =>
      new Response(
        JSON.stringify(
          url.includes('versions/')
            ? {
                count: 51,
                results: [
                  {
                    id: url.includes('page=2') ? 'old' : 'new',
                    number: url.includes('page=2') ? 1 : 51,
                    description: 'Test',
                  },
                ],
              }
            : url.endsWith('latest/')
              ? { deployment: null }
              : { count: 0, next: null, previous: null, results: [] },
        ),
      ),
  );
  render(
    <DeploymentLedger
      api={createApiClient()}
      firewallId="fw"
      role="operator"
      archived={false}
      onDirty={vi.fn()}
      onBusyChange={vi.fn()}
      onChanged={vi.fn()}
    />,
  );
  await screen.findByText('Brak wpisów dla tego filtra.');
  fireEvent.click(screen.getByRole('button', { name: 'Dodaj wpis' }));
  await screen.findByRole('option', { name: 'Wersja 51 — Test' });
  fireEvent.change(screen.getByLabelText(/Wersja konfiguracji/), { target: { value: 'new' } });
  fireEvent.click(screen.getByRole('button', { name: 'Następna strona' }));
  await screen.findByRole('option', { name: 'Wersja 1 — Test' });
  expect(screen.getByLabelText(/Wersja konfiguracji/)).toHaveValue('new');
  expect(screen.getByRole('option', { name: 'Wersja 51 — Test' })).toBeInTheDocument();
});
