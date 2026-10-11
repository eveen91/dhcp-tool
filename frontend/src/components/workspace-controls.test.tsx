import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DataForm, globalFields, subnetFields } from './workspace-controls';
afterEach(cleanup);
it('submits DNS as an array, leases as integers and empty options as null', () => {
  const submit = vi.fn();
  render(
    <DataForm
      title="Opcje"
      fields={globalFields}
      initial={{ domain: '', dns: '', default_lease_time: '', max_lease_time: '' }}
      submitLabel="Zapisz"
      busy={false}
      errors={{}}
      onDirty={() => {}}
      onSubmit={submit}
    />,
  );
  fireEvent.change(screen.getByLabelText('Serwery DNS'), {
    target: { value: '192.0.2.53, 198.51.100.53' },
  });
  fireEvent.change(screen.getByLabelText('Domyślna dzierżawa (sekundy)'), {
    target: { value: '3600' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
  expect(submit).toHaveBeenCalledWith({
    domain: null,
    dns: ['192.0.2.53', '198.51.100.53'],
    default_lease_time: 3600,
    max_lease_time: null,
  });
});

it('edits and submits every cluster interface address and clears the optional list', () => {
  const submit = vi.fn();
  render(
    <DataForm
      title="Podsieć"
      fields={subnetFields.filter((f) => f.key === 'interface_address')}
      initial={{ interface_address: ['192.0.2.2', '192.0.2.3'] }}
      submitLabel="Zapisz"
      busy={false}
      errors={{}}
      onDirty={() => {}}
      onSubmit={submit}
    />,
  );
  const input = screen.getByLabelText('Adresy interfejsów IPv4');
  expect(input).toHaveValue('192.0.2.2, 192.0.2.3');
  fireEvent.change(input, { target: { value: '192.0.2.2, 192.0.2.3 192.0.2.4' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
  expect(submit).toHaveBeenLastCalledWith({
    interface_address: ['192.0.2.2', '192.0.2.3', '192.0.2.4'],
  });
  fireEvent.change(input, { target: { value: '' } });
  fireEvent.click(screen.getByRole('button', { name: 'Zapisz' }));
  expect(submit).toHaveBeenLastCalledWith({ interface_address: null });
});
