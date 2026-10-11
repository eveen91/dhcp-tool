import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, vi, expect, it } from 'vitest';
import { CSVTransfer } from './csv-transfer';
import type { ApiClient } from '../lib/api/workspace-client';
afterEach(cleanup);

it('requires a preview and individual deletion confirmation before applying', async () => {
  const request = vi
    .fn()
    .mockResolvedValueOnce({
      token: 'signed',
      revision: 4,
      counts: { create: 0, update: 0, delete: 1, unchanged: 0 },
      changes: [
        {
          row: 2,
          operation: 'delete',
          before: { name: 'drukarka', ip: '192.0.2.10' },
          after: null,
        },
      ],
    })
    .mockResolvedValueOnce({});
  const onChanged = vi.fn();
  render(
    <CSVTransfer
      api={{ request } as unknown as ApiClient}
      firewallId="fw"
      revision={4}
      editable
      onChanged={onChanged}
      onDirty={vi.fn()}
      onError={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText('Treść CSV'), { target: { value: 'example' } });
  expect(screen.queryByRole('button', { name: 'Zastosuj import' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Sprawdź i pokaż zmiany' }));
  const apply = await screen.findByRole('button', { name: 'Zastosuj import' });
  expect(apply).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Potwierdzam usunięcie drukarka (192.0.2.10)'));
  fireEvent.click(apply);
  await waitFor(() => expect(onChanged).toHaveBeenCalled());
  expect(request).toHaveBeenLastCalledWith('/firewalls/fw/csv/config/apply/', {
    method: 'POST',
    revision: 4,
    body: { token: 'signed', confirm_deletions: true },
    signal: expect.any(AbortSignal),
  });
});

it('does not offer import to a reader', () => {
  render(
    <CSVTransfer
      api={{} as ApiClient}
      firewallId="fw"
      revision={1}
      editable={false}
      onChanged={vi.fn()}
      onDirty={vi.fn()}
      onError={vi.fn()}
    />,
  );
  expect(screen.getByRole('link', { name: 'Eksportuj konfigurację CSV' })).toHaveAttribute(
    'href',
    '/api/v1/firewalls/fw/csv/config/export/',
  );
  expect(screen.queryByLabelText('Treść CSV')).not.toBeInTheDocument();
});
