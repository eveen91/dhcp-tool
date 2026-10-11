'use client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { createApiClient, ApiError, type Schema } from '../lib/api/workspace-client';
import { HealthStatus } from './health-status';
import { DeploymentLedger } from './deployment-ledger';
import { AuditHistory } from './audit-history';
import { CSVTransfer } from './csv-transfer';
import {
  ConfirmDialog,
  DataForm,
  ErrorNotice,
  Pagination,
  globalFields,
  firewallFields,
  subnetFields,
  poolFields,
  type Field,
  type Values,
} from './workspace-controls';

type Screen =
  'configuration' | 'validation' | 'versions' | 'deployments' | 'audit' | 'administration' | 'csv';
type FormSpec = {
  title: string;
  fields: Field[];
  initial: Values;
  label: string;
  path: string;
  method: 'POST' | 'PATCH' | 'PUT';
  kind?: 'subnet' | 'login';
};
type Confirmation = {
  title: string;
  description: React.ReactNode;
  action: string;
  execute: () => Promise<void> | void;
};
const asError = (error: unknown) =>
  error instanceof ApiError
    ? error
    : new ApiError(
        0,
        'network_error',
        'Nie udało się wykonać operacji. Odśwież dane przed ponowieniem.',
      );
const syntaxLabels: Record<Schema['ValidationReport']['syntax_status'], string> = {
  syntax_checked: 'Sprawdzona',
  parser_unavailable: 'Parser niedostępny',
  syntax_error: 'Błąd składni',
  parser_error: 'Awaria parsera',
  parser_timeout: 'Przekroczony czas parsera',
};
function initials(fields: Field[], source: object): Values {
  const values = source as Values;
  return Object.fromEntries(
    fields.map((field) => [
      field.key,
      Array.isArray(values[field.key])
        ? (values[field.key] as string[]).join(', ')
        : field.key === 'gaia_host_name_fallback'
          ? values[field.key] == null
            ? ''
            : String(values[field.key])
          : (values[field.key] ?? (field.type === 'checkbox' ? false : '')),
    ]),
  );
}
function time(value: string) {
  return `${new Intl.DateTimeFormat('pl-PL', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'UTC' }).format(new Date(value))} UTC`;
}
export function Workspace() {
  const [api] = useState(createApiClient);
  const [session, setSession] = useState<Schema['Session'] | null>(null);
  const [authPrompt, setAuthPrompt] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [firewalls, setFirewalls] = useState<Schema['FirewallPage'] | null>(null);
  const [fwSearch, setFwSearch] = useState('');
  const [fwQuery, setFwQuery] = useState('');
  const [fwPage, setFwPage] = useState(1);
  const [archived, setArchived] = useState('false');
  const [selected, setSelected] = useState<Schema['Firewall'] | null>(null);
  const [draft, setDraft] = useState<Schema['Draft'] | null>(null);
  const [screen, setScreen] = useState<Screen>('configuration');
  const [subnetId, setSubnetId] = useState('');
  const [form, setForm] = useState<FormSpec | null>(null);
  const [dirty, setDirty] = useState(false);
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [refresh, setRefresh] = useState(0);
  const epoch = useRef(0);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<Schema['Preview'] | null>(null);
  const [validation, setValidation] = useState<Schema['ValidationReport'] | null>(null);
  const [versions, setVersions] = useState<Schema['VersionPage'] | null>(null);
  const [versionPage, setVersionPage] = useState(1);
  const [versionSearch, setVersionSearch] = useState('');
  const [versionQuery, setVersionQuery] = useState('');
  const [version, setVersion] = useState<Schema['VersionDetail'] | null>(null);
  const [artifact, setArtifact] = useState<string | null>(null);
  const [diff, setDiff] = useState<Schema['VersionDiff'] | null>(null);
  const [comparisonSelections, setComparisonSelections] = useState<Schema['Version'][]>([]);
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [latest, setLatest] = useState<Schema['Version'] | null>(null);
  const [deployment, setDeployment] = useState<string>('Nie można odczytać informacji');
  const [reservations, setReservations] = useState<Schema['ReservationPage'] | null>(null);
  const [resPage, setResPage] = useState(1);
  const [resSearch, setResSearch] = useState('');
  const [resQuery, setResQuery] = useState('');
  const [resActive, setResActive] = useState('');
  const [resOrder, setResOrder] = useState('name');
  const role = session?.user?.role;
  const admin = role === 'admin';
  const editable = (admin || role === 'editor') && selected?.archived === false;
  const subnet = draft?.subnets.find((item) => item.id === subnetId);
  const base = selected ? `/firewalls/${selected.id}/` : '';

  const reportError = useCallback((value: unknown) => {
    if (value instanceof Error && value.name === 'AbortError') return;
    setError(asError(value));
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    api.session(controller.signal).then(setSession).catch(reportError);
    return () => controller.abort();
  }, [api, reportError]);
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);
  useEffect(() => {
    if (!session?.user || selected || screen === 'administration') return;
    const controller = new AbortController();
    let current = true;
    setLoading(true);
    setFirewalls(null);
    const params = new URLSearchParams({
      page: String(fwPage),
      page_size: '50',
      search: fwQuery,
      ...(archived ? { archived } : {}),
    });
    api
      .request<Schema['FirewallPage']>(`/firewalls/?${params}`, { signal: controller.signal })
      .then((data) => {
        if (current) setFirewalls(data);
      })
      .catch((e) => {
        if (current) reportError(e);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, session, selected, screen, fwPage, fwQuery, archived, refresh, reportError]);
  useEffect(() => {
    if (!selected || !session?.user) return;
    const controller = new AbortController();
    let current = true;
    setLoading(true);
    setDraft(null);
    setPreview(null);
    setValidation(null);
    setVersion(null);
    setArtifact(null);
    setDiff(null);
    setLatest(null);
    setDeployment('Nie można odczytać informacji');
    const path = `/firewalls/${selected.id}/`;
    Promise.all([
      api.request<Schema['Firewall']>(path, { signal: controller.signal }),
      api.request<Schema['Draft']>(`${path}draft/`, { signal: controller.signal }),
      api.request<Schema['VersionPage']>(`${path}versions/?page_size=1`, {
        signal: controller.signal,
      }),
    ])
      .then(async ([fw, data, history]) => {
        if (!current) return;
        // Update metadata without changing the selected identity or restarting requests.
        setSelected((previous) => (previous?.id === fw.id ? fw : previous));
        setDraft(data);
        setSubnetId((previous) =>
          data.subnets.some((s) => s.id === previous) ? previous : (data.subnets[0]?.id ?? ''),
        );
        setLatest(history.results[0] ?? null);
        try {
          const result = await api.request<Schema['LatestDeployment']>(
            `${path}deployments/latest/`,
            { signal: controller.signal },
          );
          if (current)
            setDeployment(
              result.deployment
                ? `Wersja ${result.deployment.version_number} — deklaracja operatora`
                : 'Brak potwierdzonego wdrożenia',
            );
        } catch (e) {
          if (current && !(e instanceof Error && e.name === 'AbortError'))
            setDeployment('Nie można odczytać informacji');
        }
      })
      .catch((e) => {
        if (current) reportError(e);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      controller.abort();
    };
    // Identity is the dependency: refreshing metadata must not refetch recursively.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, selected?.id, session?.user?.id, refresh, reportError]);
  useEffect(() => {
    if (!base || !draft || screen !== 'configuration' || !subnetId) {
      setReservations(null);
      return;
    }
    const controller = new AbortController();
    let current = true;
    setReservations(null);
    const params = new URLSearchParams({
      page: String(resPage),
      page_size: '50',
      subnet_id: subnetId,
      search: resQuery,
      ordering: resOrder,
      ...(resActive ? { active: resActive } : {}),
    });
    api
      .request<Schema['ReservationPage']>(`${base}reservations/?${params}`, {
        signal: controller.signal,
      })
      .then((data) => {
        if (current) setReservations(data);
      })
      .catch((e) => {
        if (current) reportError(e);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, base, draft, screen, subnetId, resPage, resQuery, resOrder, resActive, reportError]);
  useEffect(() => {
    if (!base || screen !== 'versions') return;
    const controller = new AbortController();
    let current = true;
    setVersions(null);
    const params = new URLSearchParams({
      page: String(versionPage),
      page_size: '50',
      search: versionQuery,
    });
    api
      .request<Schema['VersionPage']>(`${base}versions/?${params}`, { signal: controller.signal })
      .then((data) => {
        if (current) setVersions(data);
      })
      .catch((e) => {
        if (current) reportError(e);
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, base, screen, versionPage, versionQuery, refresh, reportError]);

  function clearTransient() {
    setForm(null);
    setDirty(false);
    setError(null);
    setNotice('');
    setPreview(null);
    setValidation(null);
    setVersion(null);
    setArtifact(null);
    setDiff(null);
  }
  function navigate(action: () => void) {
    if (busy) return;
    const proceed = () => {
      epoch.current++;
      clearTransient();
      setConfirmation(null);
      action();
    };
    if (dirty)
      setConfirmation({
        title: 'Masz niezapisane zmiany',
        description:
          'Odrzucisz lokalne pola formularza. Zapisana konfiguracja pozostanie bez zmian.',
        action: 'Odrzuć i przejdź',
        execute: proceed,
      });
    else proceed();
  }
  function openFirewall(fw: Schema['Firewall']) {
    navigate(() => {
      setSelected(fw);
      setDraft(null);
      setScreen('configuration');
      setSubnetId('');
      setResPage(1);
      setResSearch('');
      setResQuery('');
      setResActive('');
      setResOrder('name');
      setVersionPage(1);
      setVersionSearch('');
      setVersionQuery('');
      setFrom('');
      setTo('');
      setComparisonSelections([]);
      setVersions(null);
    });
  }
  async function perform<T>(operation: () => Promise<T>, success: (result: T) => void) {
    if (busy) return;
    const id = epoch.current;
    setBusy(true);
    setError(null);
    setNotice('');
    try {
      const result = await operation();
      if (id === epoch.current) success(result);
    } catch (e) {
      if (id === epoch.current) reportError(e);
    } finally {
      setBusy(false);
    }
  }
  function edit(spec: FormSpec) {
    navigate(() => setForm(spec));
  }
  async function save(values: Values) {
    if (!form) return;
    if (form.kind === 'subnet' && values.gaia_host_name_fallback !== null)
      values.gaia_host_name_fallback = values.gaia_host_name_fallback === 'true';
    const spec = form;
    await perform(
      () =>
        api.request<Schema['Firewall']>(spec.path, {
          method: spec.method,
          body: values,
          ...(selected && draft ? { revision: draft.revision } : {}),
        }),
      (result) => {
        setForm(null);
        setDirty(false);
        setNotice('Zapisano zmiany.');
        if (!selected && result?.id) {
          setSelected(result);
          setScreen('configuration');
        } else setRefresh((value) => value + 1);
      },
    );
  }
  function confirmMutation(
    title: string,
    description: React.ReactNode,
    path: string,
    method: 'DELETE' | 'POST' | 'PATCH',
    body?: unknown,
    action = 'Usuń element',
  ) {
    setConfirmation({
      title: `${title} — ${selected?.name}`,
      description,
      action,
      execute: () =>
        perform(
          () => api.request(path, { method, body, revision: draft?.revision }),
          () => {
            setConfirmation(null);
            clearTransient();
            setNotice('Operacja zakończona.');
            setRefresh((value) => value + 1);
          },
        ),
    });
  }
  function deleteSubnet() {
    if (!subnet) return;
    confirmMutation(
      `Usunąć podsieć ${subnet.cidr}?`,
      <>
        <p>Usuniesz podsieć oraz wszystkie jej elementy, również nieaktywne:</p>
        <ul>
          {subnet.pool ? (
            <li>
              Pula {subnet.pool.start}–{subnet.pool.end}
            </li>
          ) : (
            <li>Brak puli</li>
          )}
          {subnet.reservations.map((r) => (
            <li key={r.id}>
              {r.name}: {r.ip}, MAC {r.mac}
            </li>
          ))}
        </ul>
        <p>
          {subnet.reservations.length} rezerwacji. Historia pozostanie zachowana. Pusta lub
          niekompletna aktywna konfiguracja zablokuje publikację.
        </p>
      </>,
      `${base}subnets/${subnet.id}/`,
      'DELETE',
      undefined,
      'Usuń podsieć i jej elementy',
    );
  }
  const comparisonOptions = [
    ...(versions?.results ?? []),
    ...comparisonSelections.filter((v) => !versions?.results.some((row) => row.id === v.id)),
  ];
  function chooseComparison(side: 'from' | 'to', id: string) {
    const row = comparisonOptions.find((v) => v.id === id);
    const other = side === 'from' ? to : from;
    setComparisonSelections((previous) => {
      const keep = previous.filter((v) => v.id === other);
      return row && !keep.some((v) => v.id === row.id) ? [...keep, row] : keep;
    });
    if (side === 'from') setFrom(id);
    else setTo(id);
  }
  const report = preview ?? validation;
  const emptyActive = draft
    ? !draft.subnets.some((s) => s.active) || draft.subnets.some((s) => s.active && !s.pool?.active)
    : true;
  async function download(v: Schema['Version']) {
    await perform(
      async () => {
        let response: Response;
        try {
          response = await fetch(`/api/v1${base}versions/${v.id}/artifact/`, {
            cache: 'no-store',
            credentials: 'same-origin',
          });
        } catch {
          throw new ApiError(0, 'network_error', 'Nie udało się pobrać pliku.');
        }
        if (!response.ok)
          throw new ApiError(response.status, 'download_error', 'Nie udało się pobrać pliku.');
        const bytes = await response.arrayBuffer();
        if (
          response.headers.get('X-Content-SHA256') !== v.sha256 ||
          bytes.byteLength !== v.artifact_bytes
        )
          throw new ApiError(
            502,
            'artifact_mismatch',
            'Metadane pobranego pliku nie odpowiadają wybranej wersji.',
          );
        if (globalThis.crypto?.subtle) {
          const digest = await crypto.subtle.digest('SHA-256', bytes);
          const hash = Array.from(new Uint8Array(digest), (byte) =>
            byte.toString(16).padStart(2, '0'),
          ).join('');
          if (hash !== v.sha256)
            throw new ApiError(
              502,
              'artifact_mismatch',
              'SHA-256 pliku nie odpowiada wybranej wersji.',
            );
        }
        return new Blob([bytes], { type: 'text/plain' });
      },
      (blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'dhcpd.conf';
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        setNotice(
          `Pobrano dhcpd.conf: ${v.firewall_name}, wersja ${v.number}, SHA-256 ${v.sha256}. Wdrożenie nie zostało zarejestrowane.`,
        );
      },
    );
  }
  async function readVersion(id: string) {
    await perform(
      async () => {
        const detail = await api.request<Schema['VersionDetail']>(`${base}versions/${id}/`);
        const response = await fetch(`/api/v1${base}versions/${id}/artifact/`, {
          cache: 'no-store',
          credentials: 'same-origin',
        });
        if (!response.ok)
          throw new ApiError(
            response.status,
            'download_error',
            'Nie udało się odczytać pliku wersji.',
          );
        return { detail, text: await response.text() };
      },
      (result) => {
        setVersion(result.detail);
        setArtifact(result.text);
        setDiff(null);
      },
    );
  }

  return (
    <div className="workspace">
      <a className="skip-link" href="#workspace-main">
        Przejdź do treści
      </a>
      <header className="app-header">
        <strong>DHCP Tool</strong>
        <div className="toolbar compact">
          <HealthStatus />
          {session?.user ? (
            <>
              <span>
                {session.user.username} · {role ?? 'bez roli'}
              </span>
              <button
                disabled={busy}
                onClick={() =>
                  navigate(() => {
                    void perform(
                      () => api.logout(),
                      () => {
                        setSession({ user: null, csrf_token: '' });
                        setSelected(null);
                        setDraft(null);
                        setFirewalls(null);
                        setVersions(null);
                        setAuthPrompt(false);
                        void api.session().then(setSession).catch(reportError);
                      },
                    );
                  })
                }
              >
                Wyloguj
              </button>
            </>
          ) : null}
        </div>
      </header>
      {session?.user ? (
        <>
          <div className="firewall-context">
            <strong>
              {selected?.name ??
                (screen === 'administration' ? 'Administracja' : 'Wybierz firewall')}
            </strong>
            {selected ? (
              <>
                <span>Gaia {selected.profile}</span>
                <span>{selected.archived ? 'Archiwalny — tylko odczyt' : 'Aktywny'}</span>
                <div className="context-states">
                  <span>Robocza: {draft ? `rewizja ${draft.revision}` : 'ładowanie'}</span>
                  <span>
                    Opublikowana:{' '}
                    {draft ? (latest ? `wersja ${latest.number}` : 'brak wersji') : 'ładowanie'}
                  </span>
                  <span>Ręcznie potwierdzona: {deployment}</span>
                </div>
              </>
            ) : null}
          </div>
          <nav className="app-nav" aria-label="Nawigacja panelu">
            <button
              disabled={busy}
              aria-current={!selected && screen !== 'administration' ? 'page' : undefined}
              onClick={() =>
                navigate(() => {
                  setSelected(null);
                  setDraft(null);
                  setScreen('configuration');
                })
              }
            >
              Lista firewalli
            </button>
            {selected
              ? (
                  [
                    ['configuration', 'Konfiguracja'],
                    ['csv', 'CSV'],
                    ['validation', 'Walidacja i podgląd'],
                    ['versions', 'Wersje'],
                    ['deployments', 'Ewidencja'],
                    ['audit', 'Historia operacji'],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    disabled={busy}
                    aria-current={screen === key ? 'page' : undefined}
                    onClick={() => navigate(() => setScreen(key))}
                  >
                    {label}
                  </button>
                ))
              : null}
            {admin ? (
              <button
                disabled={busy}
                aria-current={screen === 'administration' ? 'page' : undefined}
                onClick={() =>
                  navigate(() => {
                    setSelected(null);
                    setScreen('administration');
                  })
                }
              >
                Administracja
              </button>
            ) : null}
          </nav>
        </>
      ) : null}
      <main id="workspace-main" className="workspace-main">
        <div id="workspace-error">
          <ErrorNotice error={authPrompt || confirmation ? null : error} />
        </div>
        {error && session?.user && !authPrompt ? (
          <button disabled={busy} onClick={() => navigate(() => setRefresh((r) => r + 1))}>
            Odśwież dane
          </button>
        ) : null}
        {error?.status === 403 ? (
          <button
            onClick={() => {
              void perform(
                () => api.session(),
                () => setAuthPrompt(true),
              );
            }}
          >
            Zaloguj ponownie
          </button>
        ) : null}
        {notice ? (
          <p className="notice" role="status">
            {notice}
          </p>
        ) : null}
        {dirty ? <p className="notice warning">Niezapisane zmiany w formularzu</p> : null}
        {!session ? (
          <>
            <h1 id="workspace-title" tabIndex={-1}>
              Panel konfiguracji DHCP
            </h1>
            <p>Ładowanie sesji…</p>
            {error ? (
              <button
                onClick={() => {
                  setError(null);
                  void api.session().then(setSession).catch(reportError);
                }}
              >
                Ponów połączenie
              </button>
            ) : null}
          </>
        ) : !session.user ? (
          <>
            <h1 id="workspace-title" tabIndex={-1}>
              Logowanie
            </h1>
            {loginForm()}
          </>
        ) : (
          <>
            {screen === 'administration' ? (
              <>
                <h1 id="workspace-title" tabIndex={-1}>
                  Administracja
                </h1>
                <h2>Konta lokalne i zakres dostępu</h2>
                <p>
                  Konta i przypisania firewalli obsługują polecenia serwera{' '}
                  <code>create_local_user</code> i <code>set_user_access</code>. Role: reader,
                  editor, operator, admin. Administrator ma dostęp do wszystkich firewalli. Konta
                  autorów historii należy dezaktywować zamiast usuwać.
                </p>
                <h2>Backup do pobrania</h2>
                <p>
                  Pobierz najnowszą zaszyfrowaną kopię bazy i konfiguracji na swój komputer. Klucz
                  do odtworzenia przechowuj osobno; nie jest dołączony do pliku.
                </p>
                <p>
                  <a href="/api/v1/backups/latest/download/">Pobierz najnowszy backup</a>
                </p>
                <h2>Audyt i backupy</h2>
                <p>
                  Historię zmian przed i po operacji znajdziesz po otwarciu firewalla w zakładce
                  Historia operacji. Retencja i procedury backupu należą do konfiguracji utrzymania
                  serwera.
                </p>
              </>
            ) : !selected ? (
              <>
                <h1 id="workspace-title" tabIndex={-1}>
                  Lista firewalli
                </h1>
                <form
                  className="toolbar"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setFwQuery(fwSearch);
                    setFwPage(1);
                    setError(null);
                  }}
                >
                  <label>
                    Nazwa firewalla
                    <input value={fwSearch} onChange={(event) => setFwSearch(event.target.value)} />
                  </label>
                  <label>
                    Archiwizacja
                    <select
                      value={archived}
                      onChange={(event) => {
                        setArchived(event.target.value);
                        setFwPage(1);
                      }}
                    >
                      <option value="false">Aktywne</option>
                      <option value="true">Archiwalne</option>
                      <option value="">Wszystkie</option>
                    </select>
                  </label>
                  <button type="submit">Szukaj</button>
                </form>
                {admin ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      edit({
                        title: 'Dodaj firewall',
                        fields: firewallFields,
                        initial: {
                          name: '',
                          profile: 'R81.10',
                          location: '',
                          description: '',
                          management_address: '',
                        },
                        label: 'Utwórz firewall',
                        path: '/firewalls/',
                        method: 'POST',
                      })
                    }
                  >
                    Dodaj firewall
                  </button>
                ) : null}
                {loading ? <p aria-live="polite">Ładowanie listy…</p> : null}
                {firewalls ? (
                  <>
                    <div
                      className="table-scroll"
                      role="region"
                      aria-label="Lista firewalli"
                      tabIndex={0}
                    >
                      <table>
                        <caption>Dostępne firewalle</caption>
                        <thead>
                          <tr>
                            <th scope="col">Nazwa</th>
                            <th scope="col">Profil</th>
                            <th scope="col">Lokalizacja</th>
                            <th scope="col">Stan</th>
                            <th scope="col">Działanie</th>
                          </tr>
                        </thead>
                        <tbody>
                          {firewalls.results.map((fw) => (
                            <tr key={fw.id}>
                              <td>{fw.name}</td>
                              <td>{fw.profile}</td>
                              <td>{fw.location || '—'}</td>
                              <td>{fw.archived ? 'Archiwalny' : 'Aktywny'}</td>
                              <td>
                                <button
                                  disabled={busy}
                                  aria-label={`Otwórz ${fw.name}`}
                                  onClick={() => openFirewall(fw)}
                                >
                                  Otwórz
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!firewalls.count ? <p>Brak firewalli spełniających filtry.</p> : null}
                    <Pagination
                      page={fwPage}
                      count={firewalls.count}
                      onPage={setFwPage}
                      busy={loading || busy}
                    />
                  </>
                ) : null}
              </>
            ) : (
              <>
                {loading ? <p aria-live="polite">Ładowanie konfiguracji…</p> : null}
                {!draft && error ? (
                  <button
                    disabled={busy}
                    onClick={() => {
                      setError(null);
                      setRefresh((v) => v + 1);
                    }}
                  >
                    Ponów pobranie
                  </button>
                ) : null}
                {draft && screen === 'configuration' ? (
                  <>
                    <h1 id="workspace-title" tabIndex={-1}>
                      Konfiguracja robocza
                    </h1>
                    {emptyActive ? (
                      <p className="notice warning">
                        Publikacja zablokowana: wymagana aktywna podsieć z jedną aktywną pulą.
                      </p>
                    ) : null}
                    <div className="toolbar">
                      {editable ? (
                        <>
                          <button
                            disabled={busy}
                            onClick={() =>
                              edit({
                                title: 'Opcje globalne',
                                fields: globalFields,
                                initial: initials(globalFields, draft.settings),
                                label: 'Zapisz opcje globalne',
                                path: `${base}draft/`,
                                method: 'PATCH',
                              })
                            }
                          >
                            Edytuj opcje globalne
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              edit({
                                title: 'Dodaj podsieć',
                                fields: subnetFields,
                                initial: {
                                  name: '',
                                  cidr: '',
                                  active: true,
                                  gaia_host_name_fallback: '',
                                },
                                label: 'Utwórz podsieć',
                                path: `${base}subnets/`,
                                method: 'POST',
                                kind: 'subnet',
                              })
                            }
                          >
                            Dodaj podsieć
                          </button>
                        </>
                      ) : null}
                      {admin ? (
                        <>
                          <button
                            disabled={busy}
                            onClick={() =>
                              edit({
                                title: 'Metadane firewalla',
                                fields: firewallFields,
                                initial: initials(firewallFields, selected),
                                label: 'Zapisz firewall',
                                path: base,
                                method: 'PATCH',
                              })
                            }
                          >
                            Edytuj firewall
                          </button>
                          <button
                            disabled={busy}
                            onClick={() =>
                              navigate(() =>
                                confirmMutation(
                                  selected.archived
                                    ? 'Przywrócić aktywność firewalla?'
                                    : 'Zarchiwizować firewall?',
                                  selected.archived
                                    ? 'Konfiguracja będzie ponownie edytowalna.'
                                    : 'Konfiguracja będzie dostępna tylko do odczytu. Historia pozostanie zachowana.',
                                  base,
                                  'PATCH',
                                  { archived: !selected.archived },
                                  selected.archived ? 'Przywróć aktywność' : 'Zarchiwizuj',
                                ),
                              )
                            }
                          >
                            {selected.archived ? 'Przywróć aktywność' : 'Zarchiwizuj firewall'}
                          </button>
                        </>
                      ) : null}
                    </div>
                    <details>
                      <summary>Opcje globalne — zapisane wartości</summary>
                      <pre>{JSON.stringify(draft.settings, null, 2)}</pre>
                    </details>
                    <div className="editor-layout">
                      <aside aria-label="Podsieci">
                        <h2>Podsieci</h2>
                        {!draft.subnets.length ? (
                          <p>Brak podsieci.</p>
                        ) : (
                          <ul className="subnet-list">
                            {draft.subnets.map((s) => (
                              <li key={s.id}>
                                <button
                                  disabled={busy}
                                  aria-current={s.id === subnetId ? 'true' : undefined}
                                  onClick={() =>
                                    navigate(() => {
                                      setSubnetId(s.id);
                                      setResPage(1);
                                      setResSearch('');
                                      setResQuery('');
                                    })
                                  }
                                >
                                  <strong>{s.name}</strong>
                                  <br />
                                  <span className="address">{s.cidr}</span>
                                  <br />
                                  {s.active ? 'Aktywna' : 'Nieaktywna'}
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </aside>
                      <section>
                        {subnet ? (
                          <>
                            <h2>{subnet.name}</h2>
                            <p className="address">
                              {subnet.cidr} · Brama: {subnet.gateway ?? 'brak'}
                            </p>
                            <p>{subnet.description}</p>
                            <details>
                              <summary>Opcje podsieci — zapisane wartości</summary>
                              <pre>
                                {JSON.stringify(
                                  Object.fromEntries(
                                    subnetFields
                                      .filter(
                                        (f) => !['name', 'cidr', 'description'].includes(f.key),
                                      )
                                      .map((f) => [
                                        f.label,
                                        (subnet as unknown as Values)[f.key] ??
                                          'dziedziczenie / brak opcji',
                                      ]),
                                  ),
                                  null,
                                  2,
                                )}
                              </pre>
                            </details>
                            {editable ? (
                              <div className="toolbar">
                                <button
                                  disabled={busy}
                                  onClick={() =>
                                    edit({
                                      title: `Edytuj podsieć ${subnet.cidr}`,
                                      fields: subnetFields,
                                      initial: initials(subnetFields, subnet),
                                      label: 'Zapisz podsieć',
                                      path: `${base}subnets/${subnet.id}/`,
                                      method: 'PATCH',
                                      kind: 'subnet',
                                    })
                                  }
                                >
                                  Edytuj podsieć
                                </button>
                                <button
                                  className="danger"
                                  disabled={busy}
                                  onClick={() => navigate(deleteSubnet)}
                                >
                                  Usuń podsieć
                                </button>
                              </div>
                            ) : null}
                            <h2>Pula adresów</h2>
                            {subnet.pool ? (
                              <p className="address">
                                {subnet.pool.start}–{subnet.pool.end} ·{' '}
                                {subnet.pool.active ? 'Aktywna' : 'Nieaktywna'}
                              </p>
                            ) : (
                              <p>Brak puli.</p>
                            )}
                            {subnet.pool?.description ? <p>{subnet.pool.description}</p> : null}
                            {editable ? (
                              <div className="toolbar">
                                <button
                                  disabled={busy}
                                  onClick={() =>
                                    edit({
                                      title: `Pula w ${subnet.cidr}`,
                                      fields: poolFields,
                                      initial: subnet.pool
                                        ? initials(poolFields, subnet.pool)
                                        : { start: '', end: '', active: true, description: '' },
                                      label: 'Zapisz pulę',
                                      path: `${base}subnets/${subnet.id}/pool/`,
                                      method: 'PUT',
                                    })
                                  }
                                >
                                  {subnet.pool ? 'Edytuj pulę' : 'Dodaj pulę'}
                                </button>
                                {subnet.pool ? (
                                  <button
                                    className="danger"
                                    disabled={busy}
                                    onClick={() =>
                                      navigate(() =>
                                        confirmMutation(
                                          'Usunąć pulę?',
                                          `Usuniesz pulę ${subnet.pool?.start}–${subnet.pool?.end} z ${subnet.cidr}. Publikacja aktywnej podsieci bez puli będzie zablokowana.`,
                                          `${base}subnets/${subnet.id}/pool/`,
                                          'DELETE',
                                          undefined,
                                          'Usuń pulę',
                                        ),
                                      )
                                    }
                                  >
                                    Usuń pulę
                                  </button>
                                ) : null}
                              </div>
                            ) : null}
                            <h2>Rezerwacje</h2>
                            <form
                              className="toolbar"
                              onSubmit={(event) => {
                                event.preventDefault();
                                setResQuery(resSearch);
                                setResPage(1);
                              }}
                            >
                              <label>
                                Nazwa, IP lub MAC
                                <input
                                  value={resSearch}
                                  onChange={(e) => setResSearch(e.target.value)}
                                />
                              </label>
                              <label>
                                Aktywność
                                <select
                                  value={resActive}
                                  onChange={(e) => {
                                    setResActive(e.target.value);
                                    setResPage(1);
                                  }}
                                >
                                  <option value="">Wszystkie</option>
                                  <option value="true">Aktywne</option>
                                  <option value="false">Nieaktywne</option>
                                </select>
                              </label>
                              <label>
                                Sortowanie
                                <select
                                  value={resOrder}
                                  onChange={(e) => {
                                    setResOrder(e.target.value);
                                    setResPage(1);
                                  }}
                                >
                                  <option value="name">Nazwa rosnąco</option>
                                  <option value="-name">Nazwa malejąco</option>
                                  <option value="ip">IP rosnąco</option>
                                  <option value="-ip">IP malejąco</option>
                                  <option value="mac">MAC rosnąco</option>
                                </select>
                              </label>
                              <button type="submit">Szukaj rezerwacji</button>
                            </form>
                            {editable ? (
                              <button disabled={busy} onClick={() => reservationForm()}>
                                Dodaj rezerwację
                              </button>
                            ) : null}
                            {reservations ? (
                              <>
                                <div
                                  className="table-scroll"
                                  role="region"
                                  aria-label="Rezerwacje"
                                  tabIndex={0}
                                >
                                  <table>
                                    <caption>Rezerwacje w {subnet.cidr}</caption>
                                    <thead>
                                      <tr>
                                        <th scope="col">Nazwa</th>
                                        <th
                                          scope="col"
                                          aria-sort={
                                            resOrder === 'ip'
                                              ? 'ascending'
                                              : resOrder === '-ip'
                                                ? 'descending'
                                                : 'none'
                                          }
                                        >
                                          IP
                                        </th>
                                        <th scope="col">MAC</th>
                                        <th scope="col">Opis / stan</th>
                                        {editable ? <th scope="col">Działania</th> : null}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {reservations.results.map((r) => (
                                        <tr key={r.id}>
                                          <td>{r.name}</td>
                                          <td className="address">{r.ip}</td>
                                          <td className="address">{r.mac}</td>
                                          <td>
                                            {r.description}
                                            <br />
                                            {r.active ? 'Aktywna' : 'Nieaktywna'}
                                          </td>
                                          {editable ? (
                                            <td>
                                              <div className="toolbar compact">
                                                <button
                                                  disabled={busy}
                                                  aria-label={`Edytuj rezerwację ${r.name}`}
                                                  onClick={() => reservationForm(r)}
                                                >
                                                  Edytuj
                                                </button>
                                                <button
                                                  className="danger"
                                                  disabled={busy}
                                                  aria-label={`Usuń rezerwację ${r.name}`}
                                                  onClick={() =>
                                                    navigate(() =>
                                                      confirmMutation(
                                                        'Usunąć rezerwację?',
                                                        `${r.name}, IP ${r.ip}, MAC ${r.mac}, podsieć ${subnet.cidr}. Historia pozostanie zachowana.`,
                                                        `${base}reservations/${r.id}/`,
                                                        'DELETE',
                                                        undefined,
                                                        'Usuń rezerwację',
                                                      ),
                                                    )
                                                  }
                                                >
                                                  Usuń
                                                </button>
                                              </div>
                                            </td>
                                          ) : null}
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                                {!reservations.count ? (
                                  <p>Brak rezerwacji spełniających filtry.</p>
                                ) : null}
                                <Pagination
                                  page={resPage}
                                  count={reservations.count}
                                  onPage={setResPage}
                                  busy={busy}
                                />
                              </>
                            ) : (
                              <p>Ładowanie rezerwacji…</p>
                            )}
                          </>
                        ) : null}
                      </section>
                    </div>
                  </>
                ) : null}
                {draft && screen === 'validation' ? (
                  <>
                    <h1 id="workspace-title" tabIndex={-1}>
                      Walidacja i podgląd
                    </h1>
                    <p>Konfiguracja robocza: rewizja {draft.revision}</p>
                    <div className="toolbar">
                      <button
                        disabled={busy}
                        onClick={() => {
                          setPreview(null);
                          setValidation(null);
                          void perform(
                            () =>
                              api.request<Schema['ValidationReport']>(`${base}validation/`, {
                                method: 'POST',
                                body: {},
                                revision: draft.revision,
                              }),
                            (result) => {
                              setValidation(result);
                              setPreview(null);
                            },
                          );
                        }}
                      >
                        Sprawdź konfigurację
                      </button>
                      <button
                        disabled={busy}
                        onClick={() => {
                          setPreview(null);
                          setValidation(null);
                          void perform(
                            () =>
                              api.request<Schema['Preview']>(`${base}preview/`, {
                                method: 'POST',
                                body: {},
                                revision: draft.revision,
                              }),
                            (result) => {
                              setPreview(result);
                              setValidation(null);
                            },
                          );
                        }}
                      >
                        Pokaż cały plik
                      </button>
                    </div>
                    {report ? (
                      <div className="notice">
                        <p>
                          Dane: poprawne
                          <br />
                          Składnia ISC: {syntaxLabels[report.syntax_status]}
                          <br />
                          Zgodność Gaia: niezweryfikowana
                        </p>
                        {report.syntax_status === 'parser_unavailable' ? (
                          <p>
                            Sprawdzono dane. Nie sprawdzono składni ISC ani działania na urządzeniu.
                          </p>
                        ) : null}
                        <p>{report.artifact_bytes} bajtów · SHA-256 podglądu:</p>
                        <code className="hash">{report.sha256}</code>
                      </div>
                    ) : (
                      <p>
                        Sprawdź zapisaną konfigurację. Każda zmiana unieważnia wcześniejszy raport.
                      </p>
                    )}
                    {preview ? (
                      <pre tabIndex={0} aria-label="Cały plik konfiguracji">
                        {preview.content}
                      </pre>
                    ) : null}
                    {error?.fields && Object.keys(error.fields).length ? (
                      <div className="notice error">
                        <h2>Błędy konfiguracji</h2>
                        <ul>
                          {Object.entries(error.fields).map(([path, messages]) => (
                            <li key={path}>
                              <button onClick={() => openErrorField(path)}>
                                {path}: {messages.map((m) => m.message).join(' ')}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {editable ? (
                      <>
                        <h2>Publikacja</h2>
                        <p>
                          Publikacja tworzy niezmienną wersję do pobrania. Wdrożenie wykonuje
                          operator ręcznie.
                        </p>
                        <button
                          className="primary"
                          disabled={
                            busy || emptyActive || !report || report.revision !== draft.revision
                          }
                          onClick={() =>
                            edit({
                              title: `Opublikuj wersję — ${selected.name}, Gaia ${selected.profile}, rewizja ${draft.revision}`,
                              fields: [
                                {
                                  key: 'description',
                                  label: 'Opis zmiany',
                                  type: 'textarea',
                                  required: true,
                                  max: 2000,
                                },
                              ],
                              initial: { description: '' },
                              label: 'Opublikuj wersję',
                              path: `${base}versions/`,
                              method: 'POST',
                            })
                          }
                        >
                          Przygotuj publikację
                        </button>
                        {emptyActive ? (
                          <p className="notice warning">
                            Publikacja zablokowana: aktywna konfiguracja jest pusta lub
                            niekompletna.
                          </p>
                        ) : null}
                      </>
                    ) : null}
                  </>
                ) : null}
                {draft && screen === 'versions' ? (
                  <>
                    <h1 id="workspace-title" tabIndex={-1}>
                      Wersje
                    </h1>
                    <form
                      className="toolbar"
                      onSubmit={(e) => {
                        e.preventDefault();
                        setVersionQuery(versionSearch);
                        setVersionPage(1);
                      }}
                    >
                      <label>
                        Opis zmiany
                        <input
                          value={versionSearch}
                          onChange={(e) => setVersionSearch(e.target.value)}
                        />
                      </label>
                      <button>Szukaj wersji</button>
                    </form>
                    {versions ? (
                      <>
                        <div
                          className="table-scroll"
                          role="region"
                          aria-label="Historia wersji"
                          tabIndex={0}
                        >
                          <table>
                            <caption>Zapisane wersje — tylko odczyt</caption>
                            <thead>
                              <tr>
                                <th scope="col">Wersja</th>
                                <th scope="col">Czas</th>
                                <th scope="col">Autor</th>
                                <th scope="col">Opis</th>
                                <th scope="col">Profil</th>
                                <th scope="col">Działania</th>
                              </tr>
                            </thead>
                            <tbody>
                              {versions.results.map((v) => (
                                <tr key={v.id}>
                                  <td>{v.number}</td>
                                  <td>{time(v.created_at)}</td>
                                  <td>{v.author.username ?? 'Konto historyczne'}</td>
                                  <td>{v.description}</td>
                                  <td>{v.profile}</td>
                                  <td>
                                    <button
                                      disabled={busy}
                                      onClick={() => {
                                        void readVersion(v.id);
                                      }}
                                    >
                                      Otwórz wersję {v.number}
                                    </button>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                        {!versions.count ? <p>Brak zapisanych wersji.</p> : null}
                        <Pagination
                          page={versionPage}
                          count={versions.count}
                          onPage={setVersionPage}
                          busy={busy}
                        />
                      </>
                    ) : (
                      <p>Ładowanie wersji…</p>
                    )}
                    {version ? (
                      <section className="version-detail">
                        <h2>Wersja {version.number} — tylko odczyt</h2>
                        <p>
                          Firewall w publikacji: {version.firewall_name} · Profil historyczny:{' '}
                          {version.profile}
                          <br />
                          Autor: {version.author.username} · {time(version.created_at)}
                          <br />
                          Generator: {version.generator_version} · Rewizja źródłowa:{' '}
                          {version.revision}
                          <br />
                          {version.artifact_bytes} bajtów · Składnia ISC:{' '}
                          {syntaxLabels[version.validation.syntax_status]}
                          <br />
                          Zgodność Gaia: niezweryfikowana
                        </p>
                        <p>{version.description}</p>
                        <code className="hash">SHA-256: {version.sha256}</code>
                        <div className="toolbar">
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() => {
                              void download(version);
                            }}
                          >
                            Pobierz dhcpd.conf
                          </button>
                          {editable ? (
                            <button
                              disabled={busy}
                              onClick={() =>
                                confirmMutation(
                                  `Odtworzyć wersję ${version.number} do roboczej?`,
                                  `Zastąpisz aktualną konfigurację roboczą migawką wersji ${version.number}. Obecny profil ${selected.profile}, historia oraz ewidencja pozostaną zachowane. Urządzenie nie zostanie zmienione.`,
                                  `${base}versions/${version.id}/restore/`,
                                  'POST',
                                  {},
                                  'Odtwórz wersję do roboczej',
                                )
                              }
                            >
                              Odtwórz do konfiguracji roboczej
                            </button>
                          ) : null}
                        </div>
                        <details>
                          <summary>Pełna migawka wersji</summary>
                          <pre>{JSON.stringify(version.snapshot, null, 2)}</pre>
                        </details>
                        {artifact !== null ? (
                          <pre tabIndex={0} aria-label="Zapisany plik wersji">
                            {artifact}
                          </pre>
                        ) : null}
                      </section>
                    ) : null}
                    <h2>Porównanie wersji</h2>
                    <form
                      className="toolbar"
                      onSubmit={(e) => {
                        e.preventDefault();
                        void perform(
                          () =>
                            api.request<Schema['VersionDiff']>(
                              `${base}diff/?${new URLSearchParams({ to, ...(from ? { from } : {}) })}`,
                            ),
                          setDiff,
                        );
                      }}
                    >
                      <label>
                        Wersja bazowa
                        <select
                          value={from}
                          onChange={(e) => chooseComparison('from', e.target.value)}
                        >
                          <option value="">Ostatnia ręcznie potwierdzona</option>
                          {comparisonOptions.map((v) => (
                            <option key={v.id} value={v.id}>
                              Wersja {v.number}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Wersja docelowa
                        <select
                          required
                          value={to}
                          onChange={(e) => chooseComparison('to', e.target.value)}
                        >
                          <option value="">Wybierz wersję</option>
                          {comparisonOptions.map((v) => (
                            <option key={v.id} value={v.id}>
                              Wersja {v.number}
                            </option>
                          ))}
                        </select>
                      </label>
                      <button disabled={busy}>Porównaj</button>
                    </form>
                    {diff ? (
                      diff.from ? (
                        <>
                          <p>
                            Wersja {diff.from.number} → {diff.to.number}
                            {diff.manual_deployment ? ' · Baza: deklaracja operatora' : ''}
                          </p>
                          <h3>Zmiany obiektów</h3>
                          {!diff.semantic.length ? (
                            <p>Brak zmian danych konfiguracji.</p>
                          ) : (
                            <ul>
                              {diff.semantic.map((change, index) => (
                                <li key={index}>
                                  <strong>
                                    {change.kind === 'added'
                                      ? '+ Dodano'
                                      : change.kind === 'removed'
                                        ? '− Usunięto'
                                        : 'Zmieniono'}
                                  </strong>{' '}
                                  {change.object_type} {change.object_id} {change.field}
                                  <pre>
                                    {JSON.stringify(
                                      { przed: change.before, po: change.after },
                                      null,
                                      2,
                                    )}
                                  </pre>
                                </li>
                              ))}
                            </ul>
                          )}
                          <h3>Różnice pliku</h3>
                          <pre tabIndex={0}>{diff.text || 'Brak różnic pliku.'}</pre>
                        </>
                      ) : (
                        <p className="notice">
                          Brak potwierdzonego wdrożenia. Wybierz wersję bazową do porównania.
                        </p>
                      )
                    ) : null}
                  </>
                ) : null}
                {screen === 'deployments' ? (
                  <DeploymentLedger
                    key={selected.id}
                    api={api}
                    firewallId={selected.id}
                    role={role ?? ''}
                    archived={selected.archived}
                    onDirty={setDirty}
                    onBusyChange={setBusy}
                    onChanged={() => setRefresh((v) => v + 1)}
                    onError={reportError}
                  />
                ) : null}
                {draft && screen === 'csv' ? (
                  <CSVTransfer
                    key={`${selected.id}:${draft.revision}`}
                    api={api}
                    firewallId={selected.id}
                    revision={draft.revision}
                    editable={Boolean(editable)}
                    onDirty={setDirty}
                    onBusyChange={setBusy}
                    onError={reportError}
                    onChanged={() => {
                      setNotice('Import CSV zapisany w konfiguracji roboczej.');
                      setRefresh((v) => v + 1);
                    }}
                  />
                ) : null}
                {screen === 'audit' ? (
                  <AuditHistory key={selected.id} api={api} firewallId={selected.id} />
                ) : null}
              </>
            )}
            {form ? (
              <DataForm
                key={`${form.path}-${form.title}`}
                title={form.title}
                fields={form.fields}
                initial={form.initial}
                submitLabel={form.label}
                readOnly={!selected ? !admin : !(editable || (admin && form.path === base))}
                busy={busy}
                errors={error?.fields ?? {}}
                onDirty={setDirty}
                onCancel={() => navigate(() => setForm(null))}
                onSubmit={(values) => {
                  if (form.path.endsWith('/versions/')) {
                    void perform(
                      () =>
                        api.request<Schema['Version']>(form.path, {
                          method: 'POST',
                          body: values,
                          revision: draft?.revision,
                        }),
                      (v) => {
                        setForm(null);
                        setDirty(false);
                        setPreview(null);
                        setValidation(null);
                        setScreen('versions');
                        setLatest(v);
                        setRefresh((r) => r + 1);
                        setNotice(
                          `Opublikowano wersję ${v.number}. Otwórz ją, aby pobrać zapisany plik.`,
                        );
                      },
                    );
                  } else {
                    void save(values);
                  }
                }}
              />
            ) : null}
          </>
        )}
      </main>
      {authPrompt && session?.user ? (
        <ConfirmDialog
          title="Zaloguj ponownie"
          action=""
          busy={busy}
          onCancel={() => setAuthPrompt(false)}
          onConfirm={() => {}}
        >
          <p>Twoje lokalne pola pozostaną zachowane przy logowaniu na to samo konto.</p>
          <ErrorNotice error={error} />
          {loginForm()}
        </ConfirmDialog>
      ) : null}
      {confirmation ? (
        <ConfirmDialog
          title={confirmation.title}
          action={confirmation.action}
          busy={busy}
          onCancel={() => setConfirmation(null)}
          onConfirm={() => {
            void confirmation.execute();
          }}
        >
          {confirmation.description}
          <ErrorNotice error={error} />
        </ConfirmDialog>
      ) : null}
      <footer className="app-footer">
        Check Point Gaia · DHCPv4 · Wdrożenia wykonywane ręcznie
      </footer>
    </div>
  );

  function loginForm() {
    return (
      <DataForm
        key="login"
        title="Konto lokalne"
        fields={[
          { key: 'username', label: 'Nazwa użytkownika', required: true, max: 150 },
          { key: 'password', label: 'Hasło', type: 'password', required: true, max: 1024 },
        ]}
        initial={{ username: '', password: '' }}
        submitLabel="Zaloguj"
        busy={busy}
        errors={error?.fields ?? {}}
        onDirty={() => {}}
        onSubmit={(values) => {
          void perform(
            () =>
              api.login({
                username: String(values.username),
                password: String(values.password),
              }),
            (result) => {
              if (session?.user?.id !== result.user?.id) {
                epoch.current++;
                clearTransient();
                setSelected(null);
                setDraft(null);
                setFirewalls(null);
                setScreen('configuration');
              }
              setSession(result);
              setAuthPrompt(false);
            },
          );
        }}
      />
    );
  }

  function reservationForm(reservation?: Schema['Reservation']) {
    if (!draft || !subnet) return;
    const fields: Field[] = [
      {
        key: 'subnet_id',
        label: 'Podsieć',
        type: 'select',
        required: true,
        options: draft.subnets.map((s) => ({ value: s.id, label: `${s.name} (${s.cidr})` })),
      },
      {
        key: 'name',
        label: 'Nazwa hosta',
        required: true,
        max: 63,
        pattern: '[A-Za-z][A-Za-z0-9_-]{0,62}',
      },
      {
        key: 'ip',
        label: 'Adres IP',
        required: true,
        help: 'Adres musi należeć do podsieci i znajdować się poza pulą.',
      },
      { key: 'mac', label: 'MAC', required: true, max: 17 },
      { key: 'description', label: 'Opis', type: 'textarea', max: 1000 },
      { key: 'active', label: 'Rezerwacja aktywna', type: 'checkbox' },
    ];
    edit({
      title: reservation ? `Edytuj rezerwację ${reservation.name}` : 'Dodaj rezerwację',
      fields,
      initial: reservation
        ? initials(fields, reservation)
        : { subnet_id: subnet.id, name: '', ip: '', mac: '', description: '', active: true },
      label: 'Zapisz rezerwację',
      path: `${base}reservations/${reservation ? `${reservation.id}/` : ''}`,
      method: reservation ? 'PATCH' : 'POST',
    });
  }
  function openErrorField(path: string) {
    if (!draft) return;
    const targetSubnet = draft.subnets.find((s) => path.includes(s.id));
    const reservation = targetSubnet?.reservations.find((r) => path.includes(r.id));
    setScreen('configuration');
    if (targetSubnet) setSubnetId(targetSubnet.id);
    if (!editable) {
      setNotice('Element z błędem jest dostępny tylko do odczytu.');
      return;
    }
    if (reservation) {
      const fields: Field[] = [
        {
          key: 'subnet_id',
          label: 'Podsieć',
          type: 'select',
          required: true,
          options: draft.subnets.map((s) => ({ value: s.id, label: s.cidr })),
        },
        { key: 'name', label: 'Nazwa hosta', required: true, max: 63 },
        { key: 'ip', label: 'Adres IP', required: true },
        { key: 'mac', label: 'MAC', required: true, max: 17 },
        { key: 'description', label: 'Opis', type: 'textarea', max: 1000 },
        { key: 'active', label: 'Rezerwacja aktywna', type: 'checkbox' },
      ];
      setForm({
        title: `Rezerwacja ${reservation.name}`,
        fields,
        initial: initials(fields, reservation),
        label: 'Zapisz rezerwację',
        path: `${base}reservations/${reservation.id}/`,
        method: 'PATCH',
      });
    } else if (targetSubnet && path.includes('pool'))
      setForm({
        title: 'Pula z błędem',
        fields: poolFields,
        initial: initials(poolFields, targetSubnet.pool ?? {}),
        label: 'Zapisz pulę',
        path: `${base}subnets/${targetSubnet.id}/pool/`,
        method: 'PUT',
      });
    else if (targetSubnet)
      setForm({
        title: 'Podsieć z błędem',
        fields: subnetFields,
        initial: initials(subnetFields, targetSubnet),
        label: 'Zapisz podsieć',
        path: `${base}subnets/${targetSubnet.id}/`,
        method: 'PATCH',
        kind: 'subnet',
      });
    else
      setForm({
        title: 'Opcje globalne',
        fields: globalFields,
        initial: initials(globalFields, draft.settings),
        label: 'Zapisz opcje globalne',
        path: `${base}draft/`,
        method: 'PATCH',
      });
  }
}
