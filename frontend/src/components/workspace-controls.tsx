'use client';
import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import { ApiError, type FieldErrors } from '../lib/api/workspace-client';
export type Field = {
  key: string;
  label: string;
  type?: 'text' | 'number' | 'checkbox' | 'select' | 'textarea' | 'password';
  required?: boolean;
  max?: number;
  options?: { value: string; label: string }[];
  help?: string;
  nullable?: boolean;
  list?: boolean;
  pattern?: string;
};
export type Values = Record<string, string | number | boolean | string[] | null | undefined>;
export function errorMessage(error: ApiError) {
  if (error.status === 409 && error.code === 'revision_conflict')
    return `Konfiguracja została zmieniona. Aktualna rewizja: ${error.currentRevision ?? 'nieznana'}. Zachowano Twoje pola. Odśwież świadomie; zapis nie zostanie ponowiony automatycznie.`;
  if (error.status === 403)
    return 'Sesja wygasła lub nie masz uprawnień do tej operacji. Zaloguj się ponownie lub sprawdź dostęp.';
  if (error.status === 404) return 'Firewall lub element jest niedostępny.';
  if (error.status === 429)
    return `Zbyt wiele prób. Ponów po ${error.retryAfter ?? '900'} sekundach.`;
  return error.message;
}
export function ErrorNotice({ error }: { error: ApiError | null }) {
  return error ? (
    <div className="notice error" role="alert">
      {errorMessage(error)}
    </div>
  ) : null;
}
export function ConfirmDialog({
  title,
  children,
  action,
  busy,
  onConfirm,
  onCancel,
}: {
  title: string;
  children: ReactNode;
  action: string;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const box = useRef<HTMLDivElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    cancel.current?.focus();
    return () => {
      if (previous?.isConnected) previous.focus();
      else document.getElementById('workspace-title')?.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop">
      <div
        ref={box}
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !busy) {
            event.preventDefault();
            event.stopPropagation();
            onCancel();
          }
          if (event.key === 'Tab') {
            const items = box.current?.querySelectorAll<HTMLElement>(
              'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), [tabindex="0"]',
            );
            if (!items?.length) {
              event.preventDefault();
              return;
            }
            const first = items[0],
              last = items[items.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }
        }}
      >
        <h2 id={titleId}>{title}</h2>
        <div id={descriptionId}>{children}</div>
        <div className="toolbar">
          <button ref={cancel} disabled={busy} onClick={onCancel}>
            Anuluj
          </button>
          {action ? (
            <button className="danger" disabled={busy} onClick={onConfirm}>
              {busy ? 'Wykonywanie…' : action}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
export function DataForm({
  title,
  fields,
  initial,
  submitLabel,
  readOnly = false,
  busy,
  errors,
  onDirty,
  onValuesChange,
  onSubmit,
  onCancel,
}: {
  title: string;
  fields: Field[];
  initial: Values;
  submitLabel: string;
  readOnly?: boolean;
  busy: boolean;
  errors: FieldErrors;
  onDirty: (dirty: boolean) => void;
  onValuesChange?: (values: Values) => void;
  onSubmit: (values: Values) => void;
  onCancel?: () => void;
}) {
  const [values, setValues] = useState<Values>(initial);
  const prefix = useId();
  const summary = useRef<HTMLDivElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  useEffect(() => {
    formRef.current?.querySelector<HTMLElement>('input, select, textarea')?.focus();
  }, []);
  useEffect(() => {
    if (Object.keys(errors).length) summary.current?.focus();
  }, [errors]);
  function fieldErrors(key: string) {
    return Object.entries(errors)
      .filter(([path]) => path === key || path.endsWith(`.${key}`))
      .flatMap(([, messages]) => messages);
  }
  return (
    <section className="form-panel">
      <h2>{title}</h2>
      {Object.keys(errors).length > 0 ? (
        <div ref={summary} tabIndex={-1} className="notice error">
          <p>Popraw wskazane pola:</p>
          <ul>
            {Object.entries(errors).map(([path, messages]) => {
              const field = fields.find((f) => path === f.key || path.endsWith(`.${f.key}`));
              return (
                <li key={path}>
                  <a href={field ? `#${prefix}-${field.key}` : '#workspace-error'}>
                    {field?.label ?? path}: {messages.map((m) => m.message).join(' ')}
                  </a>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
      <form
        ref={formRef}
        onSubmit={(event) => {
          event.preventDefault();
          if (readOnly || busy) return;
          const result: Values = {};
          for (const field of fields) {
            const value = values[field.key];
            result[field.key] =
              field.type === 'checkbox'
                ? Boolean(value)
                : field.list
                  ? String(value ?? '').trim()
                    ? String(value)
                        .split(/[\s,]+/)
                        .filter(Boolean)
                    : null
                  : field.type === 'number'
                    ? value === '' || value == null
                      ? null
                      : Number(value)
                    : field.nullable && (value === '' || value === undefined)
                      ? null
                      : (value ?? '');
          }
          onSubmit(result);
        }}
      >
        <fieldset disabled={busy || readOnly}>
          <legend className="sr-only">{title}</legend>
          <div className="fields">
            {fields.map((field) => {
              const id = `${prefix}-${field.key}`;
              const messages = fieldErrors(field.key);
              const value = values[field.key];
              const props = {
                id,
                name: field.key,
                required: field.required,
                'aria-invalid': messages.length ? (true as const) : undefined,
                'aria-describedby': `${id}-help ${id}-error`,
                onChange: (
                  event: React.ChangeEvent<
                    HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement
                  >,
                ) => {
                  const next = {
                    ...values,
                    [field.key]:
                      field.type === 'checkbox'
                        ? (event.target as HTMLInputElement).checked
                        : event.target.value,
                  };
                  setValues(next);
                  onValuesChange?.(next);
                  onDirty(JSON.stringify(next) !== JSON.stringify(initial));
                },
              };
              return (
                <div className="field" key={field.key}>
                  <label htmlFor={id}>
                    {field.label}
                    {field.required ? ' — wymagane' : ''}
                  </label>
                  {field.type === 'checkbox' ? (
                    <input {...props} type="checkbox" checked={Boolean(value)} />
                  ) : field.type === 'select' ? (
                    <select {...props} value={String(value ?? '')}>
                      {field.options?.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  ) : field.type === 'textarea' ? (
                    <textarea
                      {...props}
                      value={String(value ?? '')}
                      maxLength={field.max}
                      rows={3}
                    />
                  ) : (
                    <input
                      {...props}
                      type={field.type ?? 'text'}
                      value={Array.isArray(value) ? value.join(', ') : String(value ?? '')}
                      maxLength={field.max}
                      min={field.type === 'number' ? 1 : undefined}
                      max={field.type === 'number' ? 2147483647 : undefined}
                      step={field.type === 'number' ? 1 : undefined}
                      pattern={field.pattern}
                      autoComplete={
                        field.type === 'password'
                          ? 'current-password'
                          : field.key === 'username'
                            ? 'username'
                            : 'off'
                      }
                      spellCheck={false}
                    />
                  )}
                  <small id={`${id}-help`}>
                    {field.help ??
                      (field.nullable ? 'Puste pole usuwa opcję lub przywraca dziedziczenie.' : '')}
                  </small>
                  <span className="field-error" id={`${id}-error`}>
                    {messages.map((m) => m.message).join(' ')}
                  </span>
                </div>
              );
            })}
          </div>
        </fieldset>
        {readOnly ? (
          <p className="notice warning">
            Brak uprawnień do zapisu. Lokalne pola są zachowane tylko do odczytu.
          </p>
        ) : null}
        <div className="toolbar">
          {!readOnly ? (
            <button className="primary" disabled={busy} type="submit">
              {busy ? 'Zapisywanie…' : submitLabel}
            </button>
          ) : null}
          {onCancel ? (
            <button type="button" disabled={busy} onClick={onCancel}>
              Anuluj
            </button>
          ) : null}
        </div>
      </form>
    </section>
  );
}
export function Pagination({
  page,
  count,
  onPage,
  busy,
}: {
  page: number;
  count: number;
  onPage: (page: number) => void;
  busy: boolean;
}) {
  return (
    <div className="toolbar">
      <span aria-live="polite">
        {count
          ? `Wyniki ${(page - 1) * 50 + 1}–${Math.min(page * 50, count)} z ${count}`
          : 'Brak wyników'}{' '}
        · 50 na stronę
      </span>
      <button disabled={busy || page <= 1} onClick={() => onPage(page - 1)}>
        Poprzednia strona
      </button>
      <button disabled={busy || page * 50 >= count} onClick={() => onPage(page + 1)}>
        Następna strona
      </button>
    </div>
  );
}
export const globalFields: Field[] = [
  { key: 'domain', label: 'Domena', max: 253, nullable: true },
  {
    key: 'dns',
    label: 'Serwery DNS',
    nullable: true,
    list: true,
    help: 'Od 1 do 3 adresów IPv4, oddzielonych przecinkiem. Puste: brak opcji lub dziedziczenie.',
  },
  {
    key: 'default_lease_time',
    label: 'Domyślna dzierżawa (sekundy)',
    type: 'number',
    nullable: true,
  },
  {
    key: 'max_lease_time',
    label: 'Maksymalna dzierżawa (sekundy)',
    type: 'number',
    nullable: true,
  },
];
export const firewallFields: Field[] = [
  {
    key: 'name',
    label: 'Nazwa firewalla',
    required: true,
    max: 63,
    pattern: '[A-Za-z][A-Za-z0-9_-]{0,62}',
  },
  {
    key: 'profile',
    label: 'Profil Gaia',
    type: 'select',
    options: [
      { value: 'R81.10', label: 'R81.10' },
      { value: 'R82.10', label: 'R82.10' },
    ],
  },
  { key: 'location', label: 'Lokalizacja', max: 150 },
  { key: 'management_address', label: 'IP zarządzania', nullable: true },
  { key: 'description', label: 'Opis', type: 'textarea', max: 1000 },
];
export const subnetFields: Field[] = [
  { key: 'name', label: 'Nazwa podsieci', required: true, max: 150 },
  { key: 'cidr', label: 'CIDR', required: true, max: 18 },
  { key: 'interface', label: 'Interfejs', max: 63 },
  { key: 'gateway', label: 'Brama IPv4', nullable: true },
  {
    key: 'interface_address',
    label: 'Adresy interfejsów IPv4',
    nullable: true,
    list: true,
    max: 1086,
    help: 'Adresy obu firewalli w klastrze, oddzielone przecinkiem lub spacją. Każdy adres jest wykluczony z puli i rezerwacji. Puste: brak ochrony adresów interfejsów.',
  },
  {
    key: 'gaia_host_name_fallback',
    label: 'Gaia host-name fallback',
    type: 'select',
    nullable: true,
    options: [
      { value: '', label: 'Brak opcji' },
      { value: 'true', label: 'Włączony' },
      { value: 'false', label: 'Wyłączony' },
    ],
  },
  ...globalFields,
  { key: 'description', label: 'Opis', type: 'textarea', max: 1000 },
  { key: 'active', label: 'Podsieć aktywna', type: 'checkbox' },
];
export const poolFields: Field[] = [
  { key: 'start', label: 'Początek puli', required: true },
  { key: 'end', label: 'Koniec puli', required: true },
  { key: 'description', label: 'Opis', type: 'textarea', max: 1000 },
  { key: 'active', label: 'Pula aktywna', type: 'checkbox' },
];
