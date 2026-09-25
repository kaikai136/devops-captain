import { afterEach, describe, expect, it, vi } from 'vitest';

import { apiGet, AUTH_EXPIRED_EVENT, ApiUnauthorizedError } from '../api';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('API authentication expiry handling', () => {
  it('notifies the app when a workspace request returns 401', async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal('window', { dispatchEvent });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"expired"}', { status: 401 })));

    await expect(apiGet('/api/system/roles/')).rejects.toBeInstanceOf(ApiUnauthorizedError);
    expect(dispatchEvent).toHaveBeenCalledOnce();
    expect(dispatchEvent.mock.calls[0][0]).toMatchObject({ type: AUTH_EXPIRED_EVENT });
  });

  it('does not treat a failed login attempt as an expired authenticated session', async () => {
    const dispatchEvent = vi.fn();
    vi.stubGlobal('window', { dispatchEvent });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"invalid credentials"}', { status: 401 })));

    await expect(apiGet('/api/auth/login/')).rejects.toBeInstanceOf(ApiUnauthorizedError);
    expect(dispatchEvent).not.toHaveBeenCalled();
  });
});
