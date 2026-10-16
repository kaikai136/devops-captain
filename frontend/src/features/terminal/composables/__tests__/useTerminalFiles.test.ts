import { describe, expect, it, vi } from 'vitest';
import { ApiResponseError } from '../../../../api';
import { terminalFileHash } from '../../utils/fileHash';
import type { TerminalFileContentResponse } from '../../api/terminal';
import { useTerminalFiles, type TerminalFileTarget } from '../useTerminalFiles';

const target: TerminalFileTarget = { hostId: 7, nodeName: 'demo', path: '/srv/app.py', name: 'app.py' };
function response(content: string, size = content.length) {
  return { path: target.path, filename: target.name, size, isText: true, contentType: 'text/plain', content, blob: new Blob([content]) };
}

describe('useTerminalFiles', () => {
  it('keeps conflicts separate, cancels drafts safely, and forces the current draft', async () => {
    const conflict = new ApiResponseError('changed', 409, { code: 'file_changed' });
    const write = vi.fn().mockRejectedValueOnce(conflict).mockRejectedValueOnce(conflict).mockResolvedValue({ size: 5 });
    const files = useTerminalFiles({ api: { read: vi.fn().mockResolvedValue(response('old')), write } });
    const tab = files.open(target, 'edit');
    const other = files.open({ ...target, hostId: 8 }, 'edit');
    await vi.waitFor(() => expect(tab.loading || other.loading).toBe(false));
    const baseline = tab.expectedHash;
    files.change(tab, 'draft');
    await files.save(tab);
    expect(tab.conflict).toBe(true);
    expect(other.conflict).toBe(false);
    expect(tab.saveError).toBe('');
    await files.save(tab);
    expect(write).toHaveBeenCalledTimes(1);
    files.cancelConflict(tab);
    expect(tab.conflict).toBe(false);
    expect(tab.content).toBe('draft');
    expect(tab.expectedHash).toBe(baseline);
    await files.save(tab);
    files.change(tab, 'newer');
    await files.save(tab, true);
    expect(write).toHaveBeenLastCalledWith(7, target.path, 'newer', { expectedHash: baseline, force: true });
    expect(tab.conflict || tab.dirty).toBe(false);
    files.change(tab, 'next');
    await files.save(tab);
    expect(write).toHaveBeenLastCalledWith(7, target.path, 'next', {
      expectedHash: terminalFileHash(new TextEncoder().encode('newer')), force: false,
    });
  });

  it('reloads conflicts without another prompt and preserves drafts on reload or force failure', async () => {
    const confirm = vi.fn();
    const read = vi.fn().mockResolvedValueOnce(response('old')).mockRejectedValueOnce(new Error('read denied'))
      .mockResolvedValueOnce(response('latest'));
    const write = vi.fn().mockRejectedValueOnce(new ApiResponseError('changed', 409, { code: 'file_changed' }))
      .mockRejectedValueOnce(new Error('write denied'));
    const files = useTerminalFiles({ api: { read, write }, confirm });
    const tab = files.open(target, 'edit');
    await vi.waitFor(() => expect(tab.loading).toBe(false));
    files.change(tab, 'draft');
    await files.save(tab);
    const baseline = tab.expectedHash;
    await files.save(tab, true);
    expect(tab.saveError).toBe('write denied');
    expect(tab.conflict).toBe(true);
    await files.reloadConflict(tab);
    expect(tab.content).toBe('draft');
    expect(tab.dirty).toBe(true);
    expect(tab.expectedHash).toBe(baseline);
    expect(tab.error).toBe('');
    expect(tab.saveError).toBe('read denied');
    await files.reloadConflict(tab);
    expect(tab.content).toBe('latest');
    expect(tab.expectedHash).toBe(terminalFileHash(new TextEncoder().encode('latest')));
    expect(tab.conflict || tab.dirty).toBe(false);
    expect(confirm).not.toHaveBeenCalled();
  });

  it('preserves BOM and CRLF on save and does not clear edits made during a save', async () => {
    let finish!: (value: { size: number }) => void;
    const write = vi.fn(() => new Promise<{ size: number }>(resolve => { finish = resolve; }));
    const files = useTerminalFiles({ api: { read: vi.fn().mockResolvedValue(response('\ufeffa\r\nb\r\n')), write } });
    const tab = files.open(target, 'edit');
    await vi.waitFor(() => expect(tab.loading).toBe(false));
    files.change(tab, 'a\nbb\n');
    const saving = files.save(tab);
    files.change(tab, 'a\nbbb\n');
    finish({ size: 10 });
    await saving;
    expect(write).toHaveBeenCalledWith(7, target.path, '\ufeffa\r\nbb\r\n', {
      expectedHash: terminalFileHash(new TextEncoder().encode('\ufeffa\r\nb\r\n')), force: false,
    });
    expect(tab.expectedHash).toBe(terminalFileHash(new TextEncoder().encode('\ufeffa\r\nbb\r\n')));
    expect(tab.dirty).toBe(true);
    expect(tab.content).toBe('a\nbbb\n');
  });

  it('retains separate hosts, rejects stale reads, and preserves edits when switching to preview', async () => {
    let finish!: (value: TerminalFileContentResponse) => void;
    const read = vi.fn().mockImplementationOnce(() => new Promise<TerminalFileContentResponse>(resolve => { finish = resolve; }))
      .mockResolvedValue(response('latest'));
    const files = useTerminalFiles({ api: { read, write: vi.fn() } });
    const tab = files.open(target, 'edit');
    await files.reload(tab);
    finish(response('stale'));
    await Promise.resolve();
    expect(tab.content).toBe('latest');
    files.change(tab, 'draft');
    files.open(target, 'preview');
    expect(tab.mode).toBe('edit');
    const other = files.open({ ...target, hostId: 8 }, 'edit');
    expect(files.tabs.value).toHaveLength(2);
    files.close(other);
    expect(files.activeTab.value?.content).toBe('draft');
    files.dispose();
  });

  it('loads images as read-only and releases their object URLs', async () => {
    const revoke = vi.spyOn(URL, 'revokeObjectURL');
    const files = useTerminalFiles({ api: { read: vi.fn().mockResolvedValue({ ...response('svg'), contentType: 'image/svg+xml' }), write: vi.fn() } });
    const tab = files.open({ ...target, name: 'logo.svg' }, 'edit');
    await vi.waitFor(() => expect(tab.loading).toBe(false));
    expect(tab.kind).toBe('image');
    expect(tab.mode).toBe('preview');
    const url = tab.imageUrl;
    files.close(tab);
    expect(revoke).toHaveBeenCalledWith(url);
    revoke.mockRestore();
  });
  it('keeps the content type for binary fallback details', async () => {
    const files = useTerminalFiles({ api: { read: vi.fn().mockResolvedValue({
      ...response('not utf8'), isText: false, content: null, contentType: 'application/pdf',
    }), write: vi.fn() } });
    const tab = files.open({ ...target, name: 'manual.pdf' }, 'preview');
    await vi.waitFor(() => expect(tab.loading).toBe(false));
    expect(tab.kind).toBe('binary');
    expect(tab.contentType).toBe('application/pdf');
  });
  it('deduplicates a file and changes preview into edit mode', async () => {
    const read = vi.fn().mockResolvedValue(response('print(1)'));
    const files = useTerminalFiles({ api: { read, write: vi.fn() } });
    const first = files.open(target, 'preview');
    const second = files.open(target, 'edit');
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(first).toBe(second);
    expect(files.tabs.value).toHaveLength(1);
    expect(files.activeTab.value?.mode).toBe('edit');
    expect(read).toHaveBeenCalledTimes(1);
  });

  it('cancels a closed file request and asks before closing dirty content', async () => {
    let rejectRead!: (error: unknown) => void;
    const read = vi.fn((_host: number, _path: string, options: RequestInit) => new Promise<TerminalFileContentResponse>((_resolve, reject) => {
      rejectRead = reject;
      options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
    }));
    const confirm = vi.fn().mockReturnValue(false);
    const files = useTerminalFiles({ api: { read, write: vi.fn() }, confirm });
    const tab = files.open(target, 'edit');
    files.change(tab, 'changed');
    expect(files.close(tab)).toBe(false);
    expect(confirm).toHaveBeenCalled();
    confirm.mockReturnValue(true);
    expect(files.close(tab)).toBe(true);
    expect(read).toHaveBeenCalled();
    rejectRead(new Error('late failure'));
  });

  it('keeps edits after a failed save and clears dirty state after success', async () => {
    const write = vi.fn().mockRejectedValueOnce(new Error('permission denied')).mockResolvedValueOnce({ size: 8 });
    const files = useTerminalFiles({ api: { read: vi.fn().mockResolvedValue(response('old')), write } });
    const tab = files.open(target, 'edit');
    await new Promise(resolve => setTimeout(resolve, 0));
    files.change(tab, 'new value');
    await files.save(tab);
    expect(tab.dirty).toBe(true);
    expect(tab.saveError).toContain('permission');
    await files.save(tab);
    expect(tab.dirty).toBe(false);
    expect(tab.byteSize).toBe(8);
  });
});
