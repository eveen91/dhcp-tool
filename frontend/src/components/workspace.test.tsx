import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Workspace } from './workspace';

const firewall = {
  id: 'one',
  name: 'fw-one',
  profile: 'R81.10',
  archived: false,
  created_at: '2026-10-10T10:00:00Z',
  description: '',
  location: 'Warszawa',
  management_address: null,
};
const subnet = {
  id: 'net',
  name: 'Biuro',
  cidr: '192.0.2.0/24',
  interface: '',
  description: '',
  active: true,
  created_at: '',
  pool: { id: 'pool', start: '192.0.2.100', end: '192.0.2.200', description: '', active: true },
  reservations: [
    {
      id: 'res',
      name: 'drukarka',
      ip: '192.0.2.10',
      mac: '02:00:00:00:00:10',
      description: '',
      active: true,
      subnet_id: 'net',
      created_at: '',
    },
  ],
};
const draft = {
  firewall_id: 'one',
  revision: 3,
  base_version_id: null,
  settings: {},
  subnets: [subnet],
};
function respond(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), { status });
}
function setup(
  role = 'editor',
  extra?: (url: string, init?: RequestInit) => Promise<Response> | Response | undefined,
) {
  vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
    const override = extra?.(url, init);
    if (override) return override;
    if (url.includes('health/')) return respond({ status: 'ok' });
    if (url.includes('auth/session/'))
      return respond({ user: { id: 1, username: 'seba', role }, csrf_token: 'token' });
    if (url.endsWith('/draft/')) return respond(draft);
    if (url.endsWith('/firewalls/one/')) return respond(firewall);
    if (url.includes('/versions/'))
      return respond({ count: 0, next: null, previous: null, results: [] });
    if (url.includes('/reservations/'))
      return respond({ count: 1, next: null, previous: null, results: subnet.reservations });
    return respond({ count: 1, next: null, previous: null, results: [firewall] });
  });
  render(<Workspace />);
}
async function open() {
  fireEvent.click(await screen.findByRole('button', { name: 'Otwórz fw-one' }));
  await screen.findByRole('heading', { name: 'Konfiguracja robocza' });
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it('shows only read actions for reader and persistent firewall context', async () => {
  setup('reader');
  await open();
  expect(screen.getByText('Gaia R81.10')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Dodaj podsieć' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Usuń podsieć' })).not.toBeInTheDocument();
});
it('requires confirmation including all descendants before deleting a subnet', async () => {
  let deletes = 0;
  setup('editor', (url, init) => {
    if (init?.method === 'DELETE' && url.includes('/subnets/')) {
      deletes++;
      return new Response(null, { status: 204 });
    }
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Usuń podsieć' }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByText(/192.0.2.100/)).toBeInTheDocument();
  expect(within(dialog).getByText(/drukarka/)).toBeInTheDocument();
  expect(within(dialog).getByRole('button', { name: 'Anuluj' })).toHaveFocus();
  expect(deletes).toBe(0);
  fireEvent.keyDown(dialog, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(deletes).toBe(0);
});
it('keeps entered values after revision conflict and does not retry a write', async () => {
  let writes = 0;
  setup('editor', (url, init) => {
    if (url.endsWith('/draft/') && init?.method === 'PATCH') {
      writes++;
      return respond(
        {
          error: {
            code: 'revision_conflict',
            message: 'Konflikt',
            fields: {},
            current_revision: 4,
          },
        },
        409,
      );
    }
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  fireEvent.change(screen.getByLabelText('Domena'), { target: { value: 'example.test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz opcje globalne' }));
  await screen.findByRole('alert');
  expect(screen.getByLabelText('Domena')).toHaveValue('example.test');
  expect(writes).toBe(1);
});
it('warns before leaving an unsaved form and preserves it when cancelled', async () => {
  setup();
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  fireEvent.change(screen.getByLabelText('Domena'), { target: { value: 'example.test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Lista firewalli' }));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Anuluj' }));
  expect(screen.getByLabelText('Domena')).toHaveValue('example.test');
});
it('links backend field errors to the form input', async () => {
  setup('editor', (url, init) => {
    if (url.endsWith('/draft/') && init?.method === 'PATCH')
      return respond(
        {
          error: {
            code: 'validation_error',
            message: 'Niepoprawne dane',
            fields: { domain: [{ code: 'invalid', message: 'Niepoprawna domena.' }] },
          },
        },
        400,
      );
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  fireEvent.change(screen.getByLabelText('Domena'), { target: { value: 'wrong' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz opcje globalne' }));
  await waitFor(() =>
    expect(screen.getByLabelText('Domena')).toHaveAttribute('aria-invalid', 'true'),
  );
  expect(screen.getByLabelText('Domena')).toHaveAccessibleDescription(/Niepoprawna domena/);
});
it('discards a late response after changing firewall', async () => {
  let release!: (response: Response) => void;
  setup('reader', (url) => {
    if (url.includes('/firewalls/?'))
      return respond({
        count: 2,
        next: null,
        previous: null,
        results: [firewall, { ...firewall, id: 'two', name: 'fw-two' }],
      });
    if (url.endsWith('/firewalls/one/draft/'))
      return new Promise<Response>((r) => {
        release = r;
      });
    if (url.endsWith('/firewalls/two/')) return respond({ ...firewall, id: 'two', name: 'fw-two' });
    if (url.endsWith('/firewalls/two/draft/'))
      return respond({ ...draft, firewall_id: 'two', subnets: [] });
  });
  fireEvent.click(await screen.findByRole('button', { name: 'Otwórz fw-one' }));
  await waitFor(() => expect(release).toBeDefined());
  fireEvent.click(screen.getByRole('button', { name: 'Lista firewalli' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Otwórz fw-two' }));
  await screen.findByText('Brak podsieci.');
  release(respond(draft));
  await waitFor(() => expect(screen.queryByText('Biuro')).not.toBeInTheDocument());
});
it('clears a previous preview when the next validation fails', async () => {
  let previews = 0;
  setup('editor', (url) => {
    if (url.endsWith('/preview/')) {
      previews++;
      return previews === 1
        ? respond({
            revision: 3,
            data_validated: true,
            syntax_status: 'parser_unavailable',
            parser_version: null,
            parser_return_code: null,
            gaia_compatibility: 'unverified',
            artifact_bytes: 8,
            sha256: 'a'.repeat(64),
            content: 'old file',
          })
        : respond(
            {
              error: {
                code: 'revision_conflict',
                message: 'Konflikt',
                fields: {},
                current_revision: 4,
              },
            },
            409,
          );
    }
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Walidacja i podgląd' }));
  fireEvent.click(screen.getByRole('button', { name: 'Pokaż cały plik' }));
  await screen.findByText('old file');
  fireEvent.click(screen.getByRole('button', { name: 'Pokaż cały plik' }));
  await screen.findByRole('alert');
  expect(screen.queryByText('old file')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Przygotuj publikację' })).toBeDisabled();
});
it('keeps read-only validation navigation from exposing write forms', async () => {
  setup('reader', (url) => {
    if (url.endsWith('/validation/'))
      return respond(
        {
          error: {
            code: 'validation_error',
            message: 'Błąd',
            fields: { 'subnets.net.cidr': [{ code: 'invalid', message: 'Niepoprawna podsieć.' }] },
          },
        },
        400,
      );
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Walidacja i podgląd' }));
  fireEvent.click(screen.getByRole('button', { name: 'Sprawdź konfigurację' }));
  fireEvent.click(await screen.findByRole('button', { name: /subnets.net.cidr/ }));
  expect(screen.queryByRole('button', { name: 'Zapisz podsieć' })).not.toBeInTheDocument();
});
it('asks before refreshing a conflicting form', async () => {
  setup('editor', (url, init) => {
    if (url.endsWith('/draft/') && init?.method === 'PATCH')
      return respond(
        {
          error: {
            code: 'revision_conflict',
            message: 'Konflikt',
            fields: {},
            current_revision: 4,
          },
        },
        409,
      );
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  fireEvent.change(screen.getByLabelText('Domena'), { target: { value: 'example.test' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz opcje globalne' }));
  await screen.findByRole('alert');
  fireEvent.click(screen.getByRole('button', { name: 'Odśwież dane' }));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Anuluj' }));
  expect(screen.getByLabelText('Domena')).toHaveValue('example.test');
});
it('requests the next page instead of rendering every reservation in the snapshot', async () => {
  setup('reader', (url) => {
    if (url.includes('/reservations/'))
      return respond({
        count: 5000,
        next: '?page=2',
        previous: null,
        results: url.includes('page=2')
          ? [{ ...subnet.reservations[0], id: 'next', name: 'ostatnia-na-stronie' }]
          : subnet.reservations,
      });
  });
  await open();
  await screen.findByText('drukarka');
  fireEvent.click(screen.getByRole('button', { name: 'Następna strona' }));
  await screen.findByText('ostatnia-na-stronie');
  expect(screen.queryByText('drukarka')).not.toBeInTheDocument();
  expect(screen.getByText(/Wyniki 51–100 z 5000/)).toBeInTheDocument();
});
it('hides configuration write actions for archived firewalls', async () => {
  setup('admin', (url) => {
    if (url.endsWith('/firewalls/one/')) return respond({ ...firewall, archived: true });
  });
  await open();
  expect(screen.getByText('Archiwalny — tylko odczyt')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Dodaj podsieć' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Przywróć aktywność' })).toBeInTheDocument();
});
it('moves keyboard focus to the opened form', async () => {
  setup();
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  expect(screen.getByLabelText('Domena')).toHaveFocus();
});
it('preserves local fields while the same user logs in again after access failure', async () => {
  setup('editor', (url, init) => {
    if (url.endsWith('/draft/') && init?.method === 'PATCH')
      return respond(
        { error: { code: 'permission_denied', message: 'Brak sesji', fields: {} } },
        403,
      );
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  fireEvent.change(screen.getByLabelText('Domena'), { target: { value: 'keep.example' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz opcje globalne' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Zaloguj ponownie' }));
  fireEvent.change(await screen.findByLabelText(/Nazwa użytkownika/), {
    target: { value: 'seba' },
  });
  fireEvent.change(screen.getByLabelText(/Hasło/), { target: { value: 'password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zaloguj' }));
  await waitFor(() => expect(screen.queryByLabelText(/Hasło/)).not.toBeInTheDocument());
  expect(screen.getByLabelText('Domena')).toHaveValue('keep.example');
});
it('keeps the selected comparison version visible across history pages', async () => {
  const makeVersion = (id: string, number: number) => ({
    id,
    number,
    firewall_id: 'one',
    author: { id: 1, username: 'seba' },
    created_at: '2026-10-10T10:00:00Z',
    description: 'Opis',
    profile: 'R81.10',
    generator_version: '1.0.0',
    firewall_name: 'fw-one',
    revision: 3,
    sha256: 'a'.repeat(64),
    artifact_bytes: 8,
    validation: {
      revision: 3,
      data_validated: true,
      syntax_status: 'parser_unavailable',
      parser_version: null,
      parser_return_code: null,
      gaia_compatibility: 'unverified',
      artifact_bytes: 8,
      sha256: 'a'.repeat(64),
      environment: { python: '3.13', system: 'Linux' },
    },
  });
  setup('reader', (url) => {
    if (url.includes('/versions/?'))
      return respond({
        count: 51,
        next: '?page=2',
        previous: null,
        results: [url.includes('page=2') ? makeVersion('v1', 1) : makeVersion('v51', 51)],
      });
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Wersje' }));
  await screen.findByRole('button', { name: 'Otwórz wersję 51' });
  fireEvent.change(screen.getByLabelText('Wersja docelowa'), { target: { value: 'v51' } });
  fireEvent.click(screen.getByRole('button', { name: 'Następna strona' }));
  await screen.findByRole('button', { name: 'Otwórz wersję 1' });
  expect(
    within(screen.getByLabelText('Wersja docelowa')).getByRole('option', { name: 'Wersja 51' }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText('Wersja docelowa')).toHaveValue('v51');
});
it('removes write actions when reauthentication returns a read-only role', async () => {
  setup('editor', (url, init) => {
    if (url.endsWith('/draft/') && init?.method === 'PATCH')
      return respond(
        { error: { code: 'permission_denied', message: 'Brak uprawnień', fields: {} } },
        403,
      );
    if (url.includes('auth/session/') && init?.method === 'POST')
      return respond({
        user: { id: 1, username: 'seba', role: 'reader' },
        csrf_token: 'new-token',
      });
  });
  await open();
  fireEvent.click(screen.getByRole('button', { name: 'Edytuj opcje globalne' }));
  fireEvent.change(screen.getByLabelText('Domena'), { target: { value: 'keep.example' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz opcje globalne' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Zaloguj ponownie' }));
  fireEvent.change(await screen.findByLabelText(/Nazwa użytkownika/), {
    target: { value: 'seba' },
  });
  fireEvent.change(screen.getByLabelText(/Hasło/), { target: { value: 'password' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zaloguj' }));
  await waitFor(() => expect(screen.queryByLabelText(/Hasło/)).not.toBeInTheDocument());
  expect(screen.queryByRole('button', { name: 'Zapisz opcje globalne' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Domena')).toHaveValue('keep.example');
});

it('lets an administrator download the encrypted backup from administration', async () => {
  setup('admin');
  fireEvent.click(await screen.findByRole('button', { name: 'Administracja' }));
  expect(await screen.findByRole('link', { name: 'Pobierz najnowszy backup' })).toHaveAttribute(
    'href',
    '/api/v1/backups/latest/download/',
  );
});
