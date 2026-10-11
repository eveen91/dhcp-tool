'use client';
import { useEffect, useRef, useState } from 'react';
import { type ApiClient, type ApiError, type Schema } from '../lib/api/workspace-client';
import { ErrorNotice, Pagination } from './workspace-controls';
import { ledgerError, ledgerTime } from './deployment-ledger';
const operations: Record<string, string> = {
  csv_import: 'Import CSV konfiguracji',
  create: 'Utworzenie',
  update: 'Zmiana',
  delete: 'Usunięcie',
  publish: 'Publikacja wersji',
  restore: 'Odtworzenie wersji',
  deployment_create: 'Rejestracja wdrożenia',
  deployment_correct: 'Korekta wdrożenia',
};
const objects: Record<string, string> = {
  firewall: 'Firewall',
  settings: 'Opcje globalne',
  draft: 'Konfiguracja robocza',
  subnet: 'Podsieć',
  pool: 'Pula',
  reservation: 'Rezerwacja',
  version: 'Wersja',
  deployment: 'Wdrożenie',
};
export function AuditHistory({ api, firewallId }: { api: ApiClient; firewallId: string }) {
  const base = `/firewalls/${firewallId}/audit/`;
  const [rows, setRows] = useState<Schema['AuditPage'] | null>(null);
  const [page, setPage] = useState(1);
  const [operation, setOperation] = useState('');
  const [objectType, setObjectType] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [error, setError] = useState<ApiError | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [detail, setDetail] = useState<Schema['AuditDetail'] | null>(null);
  const [detailError, setDetailError] = useState<ApiError | null>(null);
  const detailHeading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    setRows(null);
    setError(null);
    setSelectedId('');
    setDetail(null);
    const query = new URLSearchParams({
      page: String(page),
      page_size: '50',
      ...(operation ? { operation } : {}),
      ...(objectType ? { object_type: objectType } : {}),
    });
    api
      .request<Schema['AuditPage']>(`${base}?${query}`, { signal: controller.signal })
      .then((data) => {
        if (current) setRows(data);
      })
      .catch((e) => {
        if (current && e.name !== 'AbortError') setError(ledgerError(e));
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, base, page, operation, objectType, refresh]);
  useEffect(() => {
    if (!selectedId) return;
    const controller = new AbortController();
    let current = true;
    setDetail(null);
    setDetailError(null);
    api
      .request<Schema['AuditDetail']>(`${base}${selectedId}/`, { signal: controller.signal })
      .then((data) => {
        if (current) setDetail(data);
      })
      .catch((e) => {
        if (current && e.name !== 'AbortError') setDetailError(ledgerError(e));
      });
    return () => {
      current = false;
      controller.abort();
    };
  }, [api, base, selectedId, refresh]);
  useEffect(() => {
    if (detail) detailHeading.current?.focus();
  }, [detail]);
  return (
    <>
      <h1 id="workspace-title" tabIndex={-1}>
        Historia operacji
      </h1>
      <p className="muted">
        Operacje dotyczą wybranego firewalla. Historia zawiera autora, czas i wartości przed i po
        zmianie. Wpisy wdrożeń są ręcznymi deklaracjami.
      </p>
      <div className="toolbar">
        <label>
          Rodzaj operacji
          <select
            value={operation}
            onChange={(e) => {
              setOperation(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Wszystkie</option>
            {Object.entries(operations).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Rodzaj obiektu
          <select
            value={objectType}
            onChange={(e) => {
              setObjectType(e.target.value);
              setPage(1);
            }}
          >
            <option value="">Wszystkie</option>
            {Object.entries(objects).map(([key, label]) => (
              <option key={key} value={key}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button onClick={() => setRefresh((v) => v + 1)}>Odśwież historię</button>
      </div>
      <ErrorNotice error={error} />
      {rows ? (
        <>
          <div className="table-scroll">
            <table>
              <caption className="sr-only">Operacje wybranego firewalla</caption>
              <thead>
                <tr>
                  <th>Czas (UTC)</th>
                  <th>Autor</th>
                  <th>Operacja</th>
                  <th>Obiekt</th>
                  <th>Szczegóły</th>
                </tr>
              </thead>
              <tbody>
                {rows.results.map((row) => (
                  <tr key={row.id}>
                    <td>{ledgerTime(row.created_at)}</td>
                    <td>{row.actor ?? 'Konto niedostępne'}</td>
                    <td>{operations[row.operation] ?? row.operation}</td>
                    <td>
                      {objects[row.object_type] ?? row.object_type}
                      <br />
                      <code>{row.object_id}</code>
                    </td>
                    <td>
                      <button
                        aria-label={`Pokaż zmianę ${row.id}`}
                        onClick={() => setSelectedId(row.id)}
                      >
                        Przed / po
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {!rows.count ? <p>Brak operacji dla wybranych filtrów.</p> : null}
          <Pagination page={page} count={rows.count} busy={false} onPage={setPage} />
        </>
      ) : !error ? (
        <p role="status">Ładowanie historii…</p>
      ) : null}
      {selectedId ? (
        <section className="form-panel">
          <ErrorNotice error={detailError} />
          {detail ? (
            <>
              <h2 ref={detailHeading} tabIndex={-1}>
                Szczegóły operacji
              </h2>
              <p>
                {operations[detail.operation] ?? detail.operation} —{' '}
                {detail.actor ?? 'Konto niedostępne'}, {ledgerTime(detail.created_at)}
              </p>
              <p>
                Rewizja konfiguracji: {detail.revision}. Identyfikator operacji:{' '}
                <code>{detail.request_id}</code>
              </p>
              <h3>Przed zmianą</h3>
              <pre tabIndex={0}>{JSON.stringify(detail.before, null, 2)}</pre>
              <h3>Po zmianie</h3>
              <pre tabIndex={0}>{JSON.stringify(detail.after, null, 2)}</pre>
            </>
          ) : !detailError ? (
            <p role="status">Ładowanie szczegółów…</p>
          ) : null}
        </section>
      ) : null}
    </>
  );
}
