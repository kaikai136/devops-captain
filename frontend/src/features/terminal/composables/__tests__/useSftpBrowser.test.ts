import { ref } from 'vue';
import { describe, expect, it, vi } from 'vitest';

import type { TerminalFileEntry, TerminalFileProperties } from '../../types';
import {
  defaultSelectedEntry,
  formatEntrySize,
  formatProtocol,
  getSftpSessionLoadPath,
  propertiesTypeLabel,
  sortEntries,
  useSftpBrowser,
  type SftpBrowserApi,
  type SftpSession,
} from '../useSftpBrowser';

const parentEntry: TerminalFileEntry = {
  name: '..',
  type: 'directory',
  modifiedAt: '',
  path: '..',
};
const alphaEntry: TerminalFileEntry = {
  name: 'alpha.txt',
  type: 'file',
  modifiedAt: '2026/07/14 10:00',
  path: '/srv/alpha.txt',
  size: 5,
};
const betaEntry: TerminalFileEntry = {
  name: 'beta.txt',
  type: 'file',
  modifiedAt: '2026/07/14 10:01',
  path: '/srv/beta.txt',
  size: 4,
};

function properties(entry: TerminalFileEntry, overrides: Partial<TerminalFileProperties> = {}): TerminalFileProperties {
  return {
    name: entry.name,
    path: entry.path,
    directory: '/srv',
    type: entry.type,
    size: Number(entry.size || 0),
    modifiedAt: entry.modifiedAt,
    accessedAt: entry.modifiedAt,
    owner: 'root',
    group: 'root',
    uid: 0,
    gid: 0,
    permissions: entry.type === 'directory' ? 'drwxr-xr-x' : '-rw-r--r--',
    mode: entry.type === 'directory' ? 0o755 : 0o644,
    octalMode: entry.type === 'directory' ? '0755' : '0644',
    special: { setuid: false, setgid: false, sticky: false },
    ...overrides,
  };
}

function createApi(overrides: Partial<SftpBrowserApi> = {}): SftpBrowserApi {
  return {
    listFiles: vi.fn().mockResolvedValue({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry, betaEntry] }),
    listDownloadFiles: vi.fn().mockResolvedValue({ path: '/srv', protocol: 'sftp', entries: [] }),
    uploadFile: vi.fn().mockResolvedValue({ protocol: 'sftp' }),
    createEntry: vi.fn().mockResolvedValue(properties(alphaEntry)),
    deleteEntry: vi.fn().mockResolvedValue({ deleted: true }),
    renameEntry: vi.fn().mockResolvedValue(properties(alphaEntry)),
    getProperties: vi.fn().mockResolvedValue(properties(alphaEntry)),
    updateProperties: vi.fn().mockResolvedValue(properties(alphaEntry)),
    buildDownloadUrl: vi.fn().mockReturnValue('/download/raw/'),
    ...overrides,
  };
}

function createBrowser(api = createApi(), options: Record<string, unknown> = {}) {
  const session = ref<SftpSession | null>({ key: 'tab-1', hostId: 7, currentCwd: '/home/root' });
  return {
    api,
    session,
    browser: useSftpBrowser({ session, api, ...options }),
  };
}

describe('useSftpBrowser', () => {
  it('navigates typed absolute, relative, parent, and home paths through the listing API', async () => {
    const listFiles = vi.fn(async (_hostId: number, payload: { path: string }) => ({
      path: payload.path === '~' ? '/home/root' : payload.path,
      protocol: 'sftp',
      entries: [alphaEntry],
    }));
    const { browser } = createBrowser(createApi({ listFiles }));

    await browser.loadDirectory(' /srv ');
    await browser.loadDirectory('logs');
    expect(browser.path.value).toBe('/srv/logs');
    await browser.loadDirectory('..');
    expect(browser.path.value).toBe('/srv');
    await browser.loadDirectory('~');
    expect(browser.path.value).toBe('/home/root');
    expect(listFiles.mock.calls.map(([, payload]) => payload.path)).toEqual(['/srv', '/srv/logs', '~']);
  });

  it('retains the current directory and entries if a typed path cannot be opened', async () => {
    const api = createApi();
    const { browser } = createBrowser(api);
    await browser.loadDirectory('/srv');
    const previousEntries = browser.entries.value;
    vi.mocked(api.listFiles).mockRejectedValueOnce(new Error('目录不存在或无权限'));

    await browser.loadDirectory('/missing');

    expect(browser.path.value).toBe('/srv');
    expect(browser.entries.value).toBe(previousEntries);
    expect(browser.error.value).toBe('目录不存在或无权限');
    expect(browser.isLoading.value).toBe(false);
  });

  it('restores the followed cwd when switching terminal sessions even when the cwd text is unchanged', () => {
    expect(getSftpSessionLoadPath(true, true, '/home/root')).toBe('/home/root');
    expect(getSftpSessionLoadPath(false, true, '/home/root')).toBe('.');
    expect(getSftpSessionLoadPath(true, false, '/home/root')).toBe('.');
  });

  it('preserves legacy sorting, default selection, protocol labels, and size labels', () => {
    const hiddenFile = { ...alphaEntry, name: '.hidden', path: '/srv/.hidden' };
    const directory = { ...alphaEntry, name: 'logs', path: '/srv/logs', type: 'directory' as const };
    const visibleFile = { ...betaEntry, name: 'file10.txt', path: '/srv/file10.txt' };
    const earlierFile = { ...alphaEntry, name: 'file2.txt', path: '/srv/file2.txt' };

    expect(sortEntries([visibleFile, directory, parentEntry, earlierFile, hiddenFile]).map((entry) => entry.name)).toEqual([
      '..',
      '.hidden',
      'logs',
      'file2.txt',
      'file10.txt',
    ]);
    expect(defaultSelectedEntry([parentEntry, directory, visibleFile])).toBe(visibleFile);
    expect(formatProtocol('scp-enhanced')).toBe('SCP enhanced');
    expect(formatProtocol('scp')).toBe('SCP normal');
    expect(formatEntrySize(directory)).toBe('-');

    const api = createApi({ buildDownloadUrl: vi.fn().mockReturnValue('/download/raw/') });
    const { browser } = createBrowser(api);
    expect(browser.getDownloadUrl(alphaEntry)).toBe('/download/raw/');
    expect(api.buildDownloadUrl).toHaveBeenCalledWith(7, alphaEntry.path, 'auto');
    expect(propertiesTypeLabel(properties(directory))).toBe('文件夹');
  });

  it('lists the resolved current directory with the unchanged payload and loading order', async () => {
    let resolveList!: (value: { path: string; protocol: string; entries: TerminalFileEntry[] }) => void;
    const listFiles = vi.fn(() => new Promise<{ path: string; protocol: string; entries: TerminalFileEntry[] }>((resolve) => {
      resolveList = resolve;
    }));
    const { browser } = createBrowser(createApi({ listFiles }));

    const request = browser.loadDirectory('logs');

    expect(listFiles).toHaveBeenCalledWith(7, { path: 'logs' }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(browser.isLoading.value).toBe(true);
    expect(browser.error.value).toBe('');

    resolveList({ path: '/srv/logs', protocol: 'sftp', entries: [betaEntry, parentEntry, alphaEntry] });
    await request;

    expect(browser.isLoading.value).toBe(false);
    expect(browser.path.value).toBe('/srv/logs');
    expect(browser.entries.value.map((entry) => entry.name)).toEqual(['..', 'alpha.txt', 'beta.txt']);
    expect(browser.listProtocol.value).toBe('sftp');
  });

  it('deduplicates in-flight directory loads and reuses the short-lived cache', async () => {
    let resolveList!: (value: { path: string; protocol: string; entries: TerminalFileEntry[] }) => void;
    const listFiles = vi.fn(() => new Promise<{ path: string; protocol: string; entries: TerminalFileEntry[] }>((resolve) => {
      resolveList = resolve;
    }));
    const { browser } = createBrowser(createApi({ listFiles }));

    const first = browser.loadDirectory('/srv');
    const duplicate = browser.loadDirectory('/srv');
    expect(listFiles).toHaveBeenCalledTimes(1);

    resolveList({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry] });
    await Promise.all([first, duplicate]);
    await browser.loadDirectory('/srv');
    expect(listFiles).toHaveBeenCalledTimes(1);

    const forced = browser.loadDirectory('/srv', { force: true });
    expect(listFiles).toHaveBeenCalledTimes(2);
    resolveList({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry, betaEntry] });
    await forced;
    expect(browser.entries.value).toHaveLength(3);
  });

  it('aborts an obsolete directory request when navigating elsewhere', async () => {
    const signals: AbortSignal[] = [];
    const listFiles = vi.fn((
      _hostId: number,
      payload: { path: string },
      options: RequestInit = {},
    ) => {
      const signal = options.signal as AbortSignal;
      signals.push(signal);
      if (payload.path === '/first') {
        return new Promise<{ path: string; protocol: string; entries: TerminalFileEntry[] }>((_resolve, reject) => {
          signal.addEventListener('abort', () => reject(Object.assign(new Error('aborted'), { name: 'AbortError' })));
        });
      }
      return Promise.resolve({ path: '/second', protocol: 'sftp', entries: [parentEntry, betaEntry] });
    });
    const { browser } = createBrowser(createApi({ listFiles }));

    const first = browser.loadDirectory('/first');
    const second = browser.loadDirectory('/second');

    expect(signals[0].aborted).toBe(true);
    await Promise.all([first, second]);
    expect(browser.path.value).toBe('/second');
    expect(browser.error.value).toBe('');
  });

  it('refreshes after create and selects the created entry', async () => {
    const created = properties({ ...betaEntry, name: 'new-file', path: '/srv/new-file' });
    const listFiles = vi
      .fn()
      .mockResolvedValueOnce({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry] })
      .mockResolvedValueOnce({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry, { ...betaEntry, name: 'new-file', path: '/srv/new-file' }] });
    const createEntry = vi.fn().mockResolvedValue(created);
    const { browser } = createBrowser(createApi({ listFiles, createEntry }));
    await browser.loadDirectory('/srv');
    browser.openCreateDialog('file');
    browser.createDialog.value.name = 'new-file';

    await browser.saveCreateDialog();

    expect(createEntry).toHaveBeenCalledWith(7, 'create-file', {
      directory: '/srv',
      filename: 'new-file',
      octalMode: '0644',
    });
    expect(listFiles).toHaveBeenCalledTimes(2);
    expect(browser.selectedEntry.value?.path).toBe('/srv/new-file');
    expect(browser.selectedPaths.value).toEqual(new Set(['/srv/new-file']));
  });

  it('keeps the current refresh timing and selection behavior after rename and delete', async () => {
    const listFiles = vi
      .fn()
      .mockResolvedValueOnce({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry, betaEntry] })
      .mockResolvedValueOnce({ path: '/srv', protocol: 'sftp', entries: [parentEntry, { ...alphaEntry, name: 'renamed.txt', path: '/srv/renamed.txt' }, betaEntry] })
      .mockResolvedValueOnce({ path: '/srv', protocol: 'sftp', entries: [parentEntry, { ...alphaEntry, name: 'renamed.txt', path: '/srv/renamed.txt' }] });
    const renameEntry = vi.fn().mockResolvedValue(properties(alphaEntry, { name: 'renamed.txt', path: '/srv/renamed.txt' }));
    const deleteEntry = vi.fn().mockResolvedValue({ deleted: true });
    const { browser } = createBrowser(createApi({ listFiles, renameEntry, deleteEntry }));
    await browser.loadDirectory('/srv');

    browser.startRename(alphaEntry);
    browser.rename.value!.draftName = 'renamed.txt';
    await browser.saveRename();

    expect(renameEntry).toHaveBeenCalledWith(7, { path: '/srv/alpha.txt', newName: 'renamed.txt' });
    expect(browser.selectedEntry.value?.path).toBe('/srv/beta.txt');

    browser.openDeleteDialog(browser.selectedEntry.value);
    await browser.confirmDelete();

    expect(deleteEntry).toHaveBeenCalledWith(7, { path: '/srv/beta.txt' });
    expect(browser.selectedEntry.value?.path).toBe('/srv/renamed.txt');
    expect(browser.selectedPaths.value).toEqual(new Set(['/srv/renamed.txt']));
    expect(listFiles).toHaveBeenCalledTimes(3);
  });

  it('preserves properties payloads and reports operation errors in the dialog', async () => {
    const getProperties = vi.fn().mockResolvedValue(properties(alphaEntry));
    const updateProperties = vi.fn().mockRejectedValue(new Error('chmod denied'));
    const { browser } = createBrowser(createApi({ getProperties, updateProperties }));

    await browser.openProperties(alphaEntry);
    browser.propertiesDialog.value.draft.owner = 'deploy';
    browser.propertiesDialog.value.draft.group = 'ops';
    browser.propertiesDialog.value.draft.octalMode = '0750';
    await browser.saveProperties();

    expect(getProperties).toHaveBeenCalledWith(7, '/srv/alpha.txt');
    expect(updateProperties).toHaveBeenCalledWith(7, {
      path: '/srv/alpha.txt',
      owner: 'deploy',
      group: 'ops',
      octalMode: '0750',
      recursive: false,
    });
    expect(browser.propertiesDialog.value.saving).toBe(false);
    expect(browser.propertiesDialog.value.error).toBe('chmod denied');
  });

  it('uploads the unchanged payload, updates progress, then refreshes the original directory', async () => {
    const uploadFile = vi.fn().mockResolvedValue({ protocol: 'sftp' });
    const listFiles = vi.fn().mockResolvedValue({ path: '/srv', protocol: 'sftp', entries: [parentEntry, alphaEntry] });
    const { browser } = createBrowser(createApi({ uploadFile, listFiles }));
    browser.path.value = '/srv';
    const file = { name: 'a.txt' } as File;

    await browser.uploadFiles([{ file, relativePath: 'folder/a.txt' }]);

    expect(uploadFile).toHaveBeenCalledWith(7, {
      directory: '/srv',
      filename: 'a.txt',
      relativePath: 'folder/a.txt',
      file,
    }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    expect(browser.transferRecords.value[0]).toMatchObject({
      kind: 'upload',
      status: 'success',
      completedFiles: 1,
      totalFiles: 1,
      progress: 100,
    });
    expect(listFiles).toHaveBeenLastCalledWith(7, { path: '/srv' }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
  });

  it('uses the response filename for downloads and streams bytes into the selected directory', async () => {
    const writes: unknown[] = [];
    const close = vi.fn();
    const directoryHandle = {
      getFileHandle: vi.fn().mockResolvedValue({
        createWritable: vi.fn().mockResolvedValue({ write: vi.fn((value) => { writes.push(value); }), close, abort: vi.fn() }),
      }),
      getDirectoryHandle: vi.fn(),
    };
    const fetchResponse = new Response(new Uint8Array([1, 2, 3]), {
      status: 200,
      headers: {
        'Content-Disposition': "attachment; filename*=UTF-8''report%20final.txt",
        'Content-Length': '3',
      },
    });
    const fetcher = vi.fn().mockResolvedValue(fetchResponse);
    const api = createApi({ buildDownloadUrl: vi.fn().mockReturnValue('/download/raw/?path=%2Fsrv%2Falpha.txt') });
    const { browser } = createBrowser(api, {
      pickDownloadDirectory: vi.fn().mockResolvedValue(directoryHandle),
      fetcher,
    });

    await browser.downloadFiles([alphaEntry]);

    expect(api.buildDownloadUrl).toHaveBeenCalledWith(7, '/srv/alpha.txt', 'auto');
    expect(directoryHandle.getFileHandle).toHaveBeenCalledWith('report final.txt', { create: true });
    expect(fetcher).toHaveBeenCalledWith('/download/raw/?path=%2Fsrv%2Falpha.txt', expect.objectContaining({ credentials: 'include' }));
    expect(writes).toHaveLength(1);
    expect(close).toHaveBeenCalledOnce();
    expect(browser.transferRecords.value[0]).toMatchObject({ status: 'success', progress: 100, completedFiles: 1 });
  });

  it('keeps list failures in the browser error state and invokes unauthorized handling first', async () => {
    const unauthorized = new Error('登录已失效');
    const onUnauthorized = vi.fn().mockReturnValue(true);
    const { browser } = createBrowser(createApi({ listFiles: vi.fn().mockRejectedValue(unauthorized) }), { onUnauthorized });

    await browser.loadDirectory('/root');

    expect(onUnauthorized).toHaveBeenCalledWith(unauthorized);
    expect(browser.error.value).toBe('');
    expect(browser.isLoading.value).toBe(false);
  });
});
