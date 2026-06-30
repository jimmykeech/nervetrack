import { afterEach, describe, expect, it, vi } from 'vitest';
import { api } from './api';

afterEach(() => vi.unstubAllGlobals());

function mockFetch(status: number, body: unknown) {
  return vi.fn<typeof fetch>(
    async () =>
      new Response(JSON.stringify(body), {
        status,
        headers: { 'Content-Type': 'application/json' }
      })
  );
}

describe('auth api', () => {
  it('authConfig hits /api/v1/auth/config', async () => {
    const f = mockFetch(200, { mode: 'password', allow_registration: true });
    vi.stubGlobal('fetch', f);
    const cfg = await api.authConfig();
    expect(cfg.mode).toBe('password');
    expect(f.mock.calls[0][0]).toBe('/api/v1/auth/config');
  });

  it('login posts credentials', async () => {
    const f = mockFetch(200, { ok: true });
    vi.stubGlobal('fetch', f);
    await api.login('u@ex.com', 'hunter2pass');
    const [url, init] = f.mock.calls[0];
    expect(url).toBe('/api/v1/auth/login');
    expect(init?.method).toBe('POST');
    expect(JSON.parse(init?.body as string)).toEqual({
      email: 'u@ex.com',
      password: 'hunter2pass'
    });
  });
});
