'use client';
import { useEffect, useState } from 'react';
import { ApiError, type ApiClient, type Schema } from '../lib/api/workspace-client';
import {
  ConfirmDialog,
  DataForm,
  ErrorNotice,
  Pagination,
  type Field,
  type Values,
} from './workspace-controls';

export const deploymentLabels = {
  planned: 'Planowana',
  successful: 'Udana',
  failed: 'Nieudana',
  cancelled: 'Anulowana',
};
const statusOptions = Object.entries(deploymentLabels).map(([value, label]) => ({ value, label }));
export const hashLabels = {
  not_supplied: 'Nie podano',
  match: 'Zgodny z artefaktem',
  mismatch: 'Niezgodny z artefaktem',
};
export function ledgerTime(value: string) {
  return `${new Intl.DateTimeFormat('pl-PL', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'UTC' }).format(new Date(value))} UTC`;
}
export function ledgerError(error: unknown) {
  return error instanceof ApiError
    ? error
    : new ApiError(
        0,
        'network_error',
        'Nie potwierdzono wyniku operacji. Odśwież dane przed ponowieniem.',
      );
}
type Props = {
  api: ApiClient;
  firewallId: string;
  role: string;
  archived: boolean;
  onDirty: (dirty: boolean) => void;
  onBusyChange: (busy: boolean) => void;
  onChanged: () => void;
  onError?: (error: unknown) => void;
};
type Form = { entry: Schema['Deployment'] | null; initial: Values };
export function DeploymentLedger({
  api,
  firewallId,
  role,
  archived,
  onDirty,
  onBusyChange,
  onChanged,
  onError,
}: Props) {
  const base = `/firewalls/${firewallId}/`;
  const writable = !archived && (role === 'operator' || role === 'admin');
  const [rows, setRows] = useState<Schema['DeploymentPage'] | null>(null);
  const [latest, setLatest] = useState<Schema['LatestDeployment'] | null>(null);
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [chosenVersion, setChosenVersion] = useState<{ value: string; label: string } | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [versionRows, setVersionRows] = useState<Schema['VersionPage'] | null>(null);
  const [versionPage, setVersionPage] = useState(1);
  const [versionQuery, setVersionQuery] = useState('');
  const [versionSearch, setVersionSearch] = useState('');
  const [versionError, setVersionError] = useState<ApiError | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setRows(null);
    setLatest(null);
    setError(null);
    const query = new URLSearchParams({
      page: String(page),
      page_size: '50',
      ...(status ? { status } : {}),
    });
    Promise.all([
      api.request<Schema['DeploymentPage']>(`${base}deployments/?${query}`, {
        signal: controller.signal,
      }),
      api.request<Schema['LatestDeployment']>(`${base}deployments/latest/`, {
        signal: controller.signal,
      }),
    ])
      .then(([data, last]) => {
        if (current) {
          setRows(data);
          setLatest(last);
        }
      })
      .catch((e) => {
        if (current && e.name !== 'AbortError') setError(ledgerError(e));
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, base, page, status, refresh]);
  const formOpen = form !== null;
  useEffect(() => {
    if (!formOpen) return;
    const controller = new AbortController();
    let current = true;
    setVersionRows(null);
    setVersionError(null);
    const query = new URLSearchParams({
      page: String(versionPage),
      page_size: '50',
      search: versionQuery,
    });
    api
      .request<Schema['VersionPage']>(`${base}versions/?${query}`, { signal: controller.signal })
      .then((data) => {
        if (current) setVersionRows(data);
      })
      .catch((e) => {
        if (current && e.name !== 'AbortError') setVersionError(ledgerError(e));
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, base, formOpen, versionPage, versionQuery, refresh]);

  function markDirty(value: boolean) {
    setDirty(value);
    onDirty(value);
  }
  function closeForm() {
    setForm(null);
    markDirty(false);
    setError(null);
    setDiscard(false);
  }
  async function openForm(entry: Schema['Deployment'] | null) {
    setError(null);
    setNotice('');
    setVersionPage(1);
    setVersionQuery('');
    setVersionSearch('');
    setChosenVersion(null);
    if (entry) {
      setBusy(true);
      onBusyChange(true);
      try {
        const fresh = await api.request<Schema['Deployment']>(`${base}deployments/${entry.id}/`);
        setChosenVersion({
          value: fresh.version_id,
          label: `Wersja ${fresh.version_number} — bieżący wpis`,
        });
        setForm({ entry: fresh, initial: { ...fresh, correction_reason: '' } });
        markDirty(false);
      } catch (e) {
        setError(ledgerError(e));
        onError?.(e);
      } finally {
        setBusy(false);
        onBusyChange(false);
      }
    } else {
      setForm({
        entry: null,
        initial: {
          version_id: '',
          status: 'planned',
          occurred_at: new Date().toISOString(),
          note: '',
          ticket: '',
          supplied_hash: '',
        },
      });
      markDirty(false);
    }
  }
  async function save(values: Values) {
    if (!form || busy || !writable) return;
    setBusy(true);
    onBusyChange(true);
    setError(null);
    setNotice('');
    try {
      await api.request<Schema['Deployment']>(
        `${base}deployments/${form.entry ? `${form.entry.id}/` : ''}`,
        {
          method: form.entry ? 'PATCH' : 'POST',
          body: { ...values, ...(form.entry ? { expected_revision: form.entry.revision } : {}) },
        },
      );
      closeForm();
      setRefresh((v) => v + 1);
      onChanged();
      setNotice(
        'Zapisano ręczną deklarację i ślad audytu. Aplikacja nie potwierdza stanu urządzenia.',
      );
    } catch (e) {
      setError(ledgerError(e));
      onError?.(e);
    } finally {
      setBusy(false);
      onBusyChange(false);
    }
  }
  const versionOptions = (versionRows?.results ?? []).map((v) => ({
    value: v.id,
    label: `Wersja ${v.number} — ${v.description}`,
  }));
  if (chosenVersion && !versionOptions.some((v) => v.value === chosenVersion.value)) {
    versionOptions.unshift(chosenVersion);
  }
  const fields: Field[] = [
    {
      key: 'version_id',
      label: 'Wersja konfiguracji',
      type: 'select',
      required: true,
      options: [{ value: '', label: 'Wybierz wersję' }, ...versionOptions],
    },
    {
      key: 'status',
      label: 'Wynik zdarzenia',
      type: 'select',
      required: true,
      options: statusOptions,
    },
    {
      key: 'occurred_at',
      label: 'Czas zdarzenia',
      required: true,
      help: 'ISO 8601 ze strefą, np. 2026-10-10T12:30:00Z lub +02:00. Tylko plan może dotyczyć przyszłości.',
    },
    { key: 'note', label: 'Notatka', type: 'textarea', max: 2000 },
    { key: 'ticket', label: 'Numer zgłoszenia', max: 150 },
    {
      key: 'supplied_hash',
      label: 'Ręcznie podany SHA-256',
      max: 64,
      pattern: '([0-9a-fA-F]{64})?',
      help: 'Opcjonalny hash uzyskany samodzielnie. Porównujemy go tylko z zapisanym artefaktem.',
    },
    ...(form?.entry
      ? [
          {
            key: 'correction_reason',
            label: 'Uzasadnienie korekty',
            type: 'textarea' as const,
            required: true,
            max: 2000,
          },
        ]
      : []),
  ];
  return (
    <>
      <h1 id="workspace-title" tabIndex={-1}>
        Ewidencja ręcznych wdrożeń
      </h1>
      <p className="notice">
        Wpisy są deklaracjami użytkowników. Aplikacja nie przesyła plików i nie odczytuje firewalla.
        Zgodność ręcznie podanego hasha z artefaktem nie potwierdza stanu urządzenia.
      </p>
      <p>
        Ostatnie zadeklarowane udane wdrożenie:{' '}
        {latest
          ? latest.deployment
            ? `wersja ${latest.deployment.version_number}, ${ledgerTime(latest.deployment.occurred_at)}, ${latest.deployment.operator ?? 'konto niedostępne'}`
            : 'brak wpisu'
          : 'odczytywanie…'}
      </p>
      <p className="muted">
        Wpisy wsteczne są dozwolone. Ostatnie udane wdrożenie wybieramy według czasu zdarzenia,
        następnie czasu wpisu i UUID (malejąco). Ponowne użycie starszej wersji zachowuje historię i
        numerację.
      </p>
      <ErrorNotice error={error} />
      {notice ? (
        <p role="status" className="notice">
          {notice}
        </p>
      ) : null}
      {form ? (
        <>
          <p>
            Operator i czas wpisu są zapisywane przez serwer.
            {form.entry
              ? ` Korygujesz rewizję ${form.entry.revision}. Poprzednie wartości i uzasadnienie trafią do historii operacji.`
              : ''}
          </p>
          <form
            className="toolbar"
            onSubmit={(e) => {
              e.preventDefault();
              setVersionPage(1);
              setVersionQuery(versionSearch);
            }}
          >
            <label>
              Szukaj wersji po opisie
              <input
                value={versionSearch}
                onChange={(e) => setVersionSearch(e.target.value)}
                disabled={busy}
              />
            </label>
            <button disabled={busy}>Szukaj wersji</button>
          </form>
          <ErrorNotice error={versionError} />
          {versionError ? (
            <button disabled={busy} onClick={() => setRefresh((v) => v + 1)}>
              Ponów pobranie wersji
            </button>
          ) : null}
          {!versionRows && !versionError ? <p role="status">Ładowanie wersji…</p> : null}
          {versionRows ? (
            <Pagination
              page={versionPage}
              count={versionRows.count}
              busy={busy}
              onPage={setVersionPage}
            />
          ) : null}
          <DataForm
            key={form.entry?.id ?? 'new'}
            title={form.entry ? 'Korekta wpisu' : 'Nowy wpis wdrożenia'}
            fields={fields}
            initial={form.initial}
            submitLabel={form.entry ? 'Zapisz korektę' : 'Zapisz wpis'}
            readOnly={!writable}
            busy={busy || !versionRows}
            errors={error?.fields ?? {}}
            onDirty={markDirty}
            onValuesChange={(values) =>
              setChosenVersion(versionOptions.find((v) => v.value === values.version_id) ?? null)
            }
            onSubmit={(values) => void save(values)}
          />
          <button disabled={busy} onClick={() => (dirty ? setDiscard(true) : closeForm())}>
            Anuluj formularz
          </button>
        </>
      ) : (
        <>
          <div className="toolbar">
            {writable ? (
              <button disabled={busy} onClick={() => void openForm(null)}>
                Dodaj wpis
              </button>
            ) : (
              <p className="muted">
                Rejestracja i korekty wymagają roli operatora lub administratora oraz aktywnego
                firewalla.
              </p>
            )}
            <label>
              Filtr wyniku
              <select
                value={status}
                disabled={busy}
                onChange={(e) => {
                  setStatus(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">Wszystkie</option>
                {statusOptions.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </label>
            <button disabled={busy} onClick={() => setRefresh((v) => v + 1)}>
              Odśwież ewidencję
            </button>
          </div>
          {rows ? (
            <>
              <div className="table-scroll">
                <table>
                  <caption className="sr-only">Ręczne deklaracje wdrożeń</caption>
                  <thead>
                    <tr>
                      <th>Wersja / wynik</th>
                      <th>Zdarzenie / wpis (UTC)</th>
                      <th>Operator</th>
                      <th>Zgłoszenie / notatka</th>
                      <th>Ręczny hash</th>
                      <th>Operacje</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.results.map((row) => (
                      <tr key={row.id}>
                        <td>
                          Wersja {row.version_number}
                          <br />
                          {deploymentLabels[row.status]}
                          <br />
                          {row.profile}
                        </td>
                        <td>
                          {ledgerTime(row.occurred_at)}
                          <br />
                          <span className="muted">Wpis: {ledgerTime(row.created_at)}</span>
                        </td>
                        <td>{row.operator ?? 'Konto niedostępne'}</td>
                        <td>
                          {row.ticket || '—'}
                          <br />
                          {row.note}
                        </td>
                        <td>
                          <span
                            className={row.hash_comparison === 'mismatch' ? 'notice error' : ''}
                          >
                            {hashLabels[row.hash_comparison]}
                          </span>
                          {row.supplied_hash ? (
                            <details>
                              <summary>Pokaż hashe</summary>
                              <p>Ręcznie podany:</p>
                              <code className="hash">{row.supplied_hash}</code>
                              <p>Artefakt:</p>
                              <code className="hash">{row.artifact_sha256}</code>
                            </details>
                          ) : null}
                        </td>
                        <td>
                          {writable ? (
                            <button
                              disabled={busy}
                              aria-label={`Skoryguj wpis wersji ${row.version_number} ${row.ticket || row.id}`}
                              onClick={() => void openForm(row)}
                            >
                              Skoryguj
                            </button>
                          ) : (
                            'Tylko odczyt'
                          )}
                          <br />
                          <span className="muted">Rewizja {row.revision}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!rows.count ? <p>Brak wpisów dla tego filtra.</p> : null}
              <Pagination page={page} count={rows.count} busy={busy} onPage={setPage} />
            </>
          ) : !error ? (
            <p role="status">Ładowanie ewidencji…</p>
          ) : null}
        </>
      )}
      {discard ? (
        <ConfirmDialog
          title="Masz niezapisane zmiany"
          action="Odrzuć formularz"
          busy={busy}
          onCancel={() => setDiscard(false)}
          onConfirm={closeForm}
        >
          Odrzucisz lokalne pola wpisu. Czy kontynuować?
        </ConfirmDialog>
      ) : null}
    </>
  );
}
