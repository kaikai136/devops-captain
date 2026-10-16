import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiResponseError } from '../../../../api';
import { updateTerminalFileContent } from '../terminal';

afterEach(() => vi.unstubAllGlobals());

describe('terminal file saves', () => {
  it('sends the baseline and explicit force flag in multipart form', async () => {
    const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify({ size: 3 }), { status: 200 }));
    vi.stubGlobal('fetch', fetch);
    for (const force of [false, true]) {
      await updateTerminalFileContent(7, '/srv/test.txt', 'new', { expectedHash: 'a'.repeat(64), force });
      const [url, options] = fetch.mock.lastCall!;
      expect(url).toContain('/hosts/7/files/content/update/');
      expect(options.method).toBe('POST');
      expect(options.body.get('path')).toBe('/srv/test.txt');
      expect(options.body.get('expected_hash')).toBe('a'.repeat(64));
      expect(options.body.get('force')).toBe(String(force));
      expect(await options.body.get('file').text()).toBe('new');
    }
  });

  it('preserves the conflict status and machine-readable code', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'file_changed', error: 'changed' }), { status: 409 })));
    const saving = updateTerminalFileContent(7, '/srv/test.txt', 'new', { expectedHash: 'a'.repeat(64) });
    await expect(saving).rejects.toBeInstanceOf(ApiResponseError);
    await expect(saving).rejects.toMatchObject({ status: 409, payload: { code: 'file_changed' } });
  });
});
