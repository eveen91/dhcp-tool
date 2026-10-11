import { afterEach, describe, expect, it, vi } from 'vitest';
import { getHealth } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('getHealth', () => {
  it('returns a validated health response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"status":"ok"}')));
    await expect(getHealth()).resolves.toEqual({ status: 'ok' });
  });

  it('rejects malformed API responses instead of reporting availability', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"status":"down"}')));
    await expect(getHealth()).rejects.toThrow();
  });

  it('rejects unsuccessful HTTP responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{"status":"ok"}', { status: 503 })),
    );
    await expect(getHealth()).rejects.toThrow();
  });
});
