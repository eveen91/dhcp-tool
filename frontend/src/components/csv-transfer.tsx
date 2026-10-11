'use client';
import { useEffect, useRef, useState } from 'react';
import { ApiError, type ApiClient } from '../lib/api/workspace-client';
import { ErrorNotice } from './workspace-controls';

type RecordData = {
  kind?: string;
  start?: string;
  end?: string;
  interface?: string;
  options?: string;
  name?: string;
  ip?: string;
  mac?: string;
  subnet_cidr?: string;
  description?: string;
  active?: boolean | string;
};
type Preview = {
  token: string;
  revision: number;
  counts: { create: number; update: number; delete: number; unchanged: number };
  changes: {
    row: number;
    operation: 'create' | 'update' | 'delete';
    before: RecordData | null;
    after: RecordData | null;
  }[];
};
type Props = {
  api: ApiClient;
  firewallId: string;
  revision: number;
  editable: boolean;
  onChanged: () => void;
  onDirty: (dirty: boolean) => void;
  onError: (error: ApiError) => void;
  onBusyChange?: (busy: boolean) => void;
};
const labels = { create: 'Dodanie', update: 'Zmiana', delete: 'Usunięcie' };
const kinds: Record<string, string> = {
  firewall: 'Firewall',
  settings: 'Opcje globalne',
  subnet: 'Podsieć',
  pool: 'Pula',
  reservation: 'Rezerwacja',
};
function record(data: RecordData | null) {
  if (!data) return '—';
  const entries = [
    ['Typ', kinds[data.kind || 'reservation']],
    ['Nazwa', data.name],
    ['Podsieć', data.subnet_cidr],
    ['IP', data.ip],
    ['MAC', data.mac],
    ['Pula', data.start ? `${data.start} – ${data.end}` : undefined],
    ['Interfejs', data.interface],
    ['Opcje', data.options],
    ['Opis', data.description],
    [
      'Aktywna',
      data.active === undefined || data.active === ''
        ? undefined
        : data.active === true || String(data.active) === 'true'
          ? 'Tak'
          : 'Nie',
    ],
  ].filter(([, value]) => value !== undefined && value !== '');
  return (
    <dl>
      {entries.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
export function CSVTransfer({
  api,
  firewallId,
  revision,
  editable,
  onChanged,
  onDirty,
  onError,
  onBusyChange,
}: Props) {
  const [csv, setCSV] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmed, setConfirmed] = useState<number[]>([]);
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const controller = useRef(new AbortController());
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    controller.current = new AbortController();
    return () => controller.current.abort();
  }, []);
  useEffect(() => {
    if (preview) heading.current?.focus();
  }, [preview]);
  const base = `/firewalls/${firewallId}/csv/config/`;
  const deletes = preview?.changes.filter((change) => change.operation === 'delete') ?? [];
  const allConfirmed = deletes.every((change) => confirmed.includes(change.row));
  function change(value: string) {
    setCSV(value);
    setPreview(null);
    setConfirmed([]);
    setError(null);
    setPage(1);
    onDirty(value.length > 0);
  }
  function report(value: unknown) {
    const failure =
      value instanceof ApiError
        ? value
        : new ApiError(0, 'csv_error', 'Nie udało się odczytać lub przesłać CSV.');
    setError(failure);
    onError(failure);
  }
  async function run(apply: boolean) {
    if (busy) return;
    setBusy(true);
    onBusyChange?.(true);
    setError(null);
    const signal = controller.current.signal;
    try {
      const result = await api.request<Preview>(`${base}${apply ? 'apply' : 'preview'}/`, {
        method: 'POST',
        revision,
        body: apply ? { token: preview?.token, confirm_deletions: allConfirmed } : { csv },
        signal,
      });
      if (signal.aborted) return;
      if (apply) {
        onDirty(false);
        setCSV('');
        setPreview(null);
        onChanged();
      } else {
        setPreview(result);
        setConfirmed([]);
        setPage(1);
      }
    } catch (failure) {
      if (!signal.aborted) {
        setPreview(null);
        report(failure);
      }
    } finally {
      if (!signal.aborted) {
        setBusy(false);
        onBusyChange?.(false);
      }
    }
  }
  async function load(file: File | undefined) {
    if (!file || busy) return;
    const signal = controller.current.signal;
    change('');
    if (file.size > 32768) {
      report(new ApiError(413, 'request_too_large', 'CSV może mieć maksymalnie 32 KiB.'));
      return;
    }
    setBusy(true);
    onBusyChange?.(true);
    try {
      const text = await file.text();
      if (!signal.aborted) change(text);
    } catch (failure) {
      if (!signal.aborted) report(failure);
    } finally {
      if (!signal.aborted) {
        setBusy(false);
        onBusyChange?.(false);
      }
    }
  }
  return (
    <>
      <h1 id="workspace-title" tabIndex={-1}>
        Import i eksport CSV konfiguracji
      </h1>
      <p>
        Eksport obejmuje metadane, opcje globalne, podsieci, pule i rezerwacje wybranego firewalla.
        Import zmienia konfigurację roboczą; nie publikuje wersji ani nie oznacza wdrożenia.
      </p>
      <p>
        <a href={`/api/v1${base}export/`}>Eksportuj konfigurację CSV</a>
      </p>
      {editable ? (
        <section className="form-panel" aria-label="Import konfiguracji">
          <h2>Przygotuj import</h2>
          <p>
            Użyj nagłówka z eksportu. Pole kind określa typ: firewall, settings, subnet, pool lub
            reservation. Pole options zawiera JSON z dozwolonymi opcjami. Operacja upsert dodaje lub
            zmienia element; delete usuwa wskazany identyfikator. Pusty id oznacza nowy element.
            Usunięcie podsieci usuwa także jej pulę i rezerwacje. Metadane firewalla może zmieniać
            tylko admin. Brak wiersza nie usuwa danych. Limit: 32 KiB i 500 wierszy. Podgląd jest
            ważny przez 10 minut.
          </p>
          <label>
            Plik CSV
            <input
              type="file"
              accept=".csv,text/csv"
              disabled={busy}
              onChange={(event) => {
                void load(event.target.files?.[0]);
                event.target.value = '';
              }}
            />
          </label>
          <label>
            Treść CSV
            <textarea
              value={csv}
              rows={8}
              disabled={busy}
              onChange={(event) => change(event.target.value)}
            />
          </label>
          <button disabled={busy || !csv.trim()} onClick={() => void run(false)}>
            Sprawdź i pokaż zmiany
          </button>
          {error ? <ErrorNotice error={error} /> : null}
          {preview ? (
            <section aria-labelledby="csv-preview-title">
              <h2 id="csv-preview-title" tabIndex={-1} ref={heading}>
                Podgląd zmian CSV
              </h2>
              <p>
                Dodania: {preview.counts.create}. Zmiany: {preview.counts.update}. Usunięcia:{' '}
                {preview.counts.delete}. Bez zmian: {preview.counts.unchanged}.
              </p>
              <div className="table-scroll" role="region" aria-label="Zmiany CSV" tabIndex={0}>
                <table className="csv-preview-table">
                  <caption>Zmiany przed zapisaniem konfiguracji roboczej</caption>
                  <thead>
                    <tr>
                      <th>Wiersz</th>
                      <th>Operacja</th>
                      <th>Przed</th>
                      <th>Po</th>
                      <th>Potwierdzenie</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.changes.slice((page - 1) * 50, page * 50).map((item) => (
                      <tr key={item.row}>
                        <td>{item.row}</td>
                        <td>{labels[item.operation]}</td>
                        <td>{record(item.before)}</td>
                        <td>{record(item.after)}</td>
                        <td>
                          {item.operation === 'delete' ? (
                            <label>
                              <input
                                type="checkbox"
                                disabled={busy}
                                checked={confirmed.includes(item.row)}
                                onChange={(event) =>
                                  setConfirmed((previous) =>
                                    event.target.checked
                                      ? [...previous, item.row]
                                      : previous.filter((row) => row !== item.row),
                                  )
                                }
                              />
                              Potwierdzam usunięcie{' '}
                              {item.before?.kind ? `${kinds[item.before.kind]}: ` : ''}
                              {item.before?.name} ({item.before?.ip || item.before?.subnet_cidr})
                            </label>
                          ) : (
                            '—'
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {preview.changes.length > 50 ? (
                <div className="toolbar">
                  <button disabled={busy || page === 1} onClick={() => setPage(page - 1)}>
                    Poprzednie zmiany
                  </button>
                  <span>Strona {page}</span>
                  <button
                    disabled={busy || page * 50 >= preview.changes.length}
                    onClick={() => setPage(page + 1)}
                  >
                    Następne zmiany
                  </button>
                </div>
              ) : null}
              <button
                disabled={busy || !preview.changes.length || !allConfirmed}
                onClick={() => void run(true)}
              >
                Zastosuj import
              </button>
            </section>
          ) : null}
        </section>
      ) : (
        <p>Import wymaga roli editor lub admin i aktywnego firewalla.</p>
      )}
    </>
  );
}
