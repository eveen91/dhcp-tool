import type { components } from './schema';

type Health = components['schemas']['Health'];

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const response = await fetch('/api/v1/health/', {
    signal,
    cache: 'no-store',
    credentials: 'same-origin',
  });
  if (!response.ok) throw new Error('Health request failed');
  const data: unknown = await response.json();
  if (typeof data !== 'object' || data === null || !('status' in data) || data.status !== 'ok') {
    throw new Error('Invalid health response');
  }
  return { status: 'ok' };
}
