import { afterEach, describe, expect, it, vi } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import { chooseExportDestination, saveExport, type LocalDirectory } from '../utils/exportDestination';

afterEach(() => vi.unstubAllGlobals());

describe('local export destination', () => {
  it('requests directory permission before export and propagates cancellation', async () => {
    const directory = { name: 'exports' };
    const picker = vi.fn().mockResolvedValue(directory);
    vi.stubGlobal('window', { showDirectoryPicker: picker });
    expect(await chooseExportDestination('tele.zip')).toEqual({ kind: 'directory', handle: directory });
    expect(picker).toHaveBeenCalledWith({ mode: 'readwrite' });
    picker.mockRejectedValueOnce(new DOMException('cancel', 'AbortError'));
    await expect(chooseExportDestination('tele.zip')).rejects.toMatchObject({ name: 'AbortError' });
  });

  it('selects ZIP saving when directory selection is unavailable and reports browser download fallback', async () => {
    const file = { name: 'tele.zip' };
    vi.stubGlobal('window', { showSaveFilePicker: vi.fn().mockResolvedValue(file) });
    expect(await chooseExportDestination('tele.zip')).toEqual({ kind: 'zip', handle: file });
    vi.stubGlobal('window', {});
    expect(await chooseExportDestination('tele.zip')).toEqual({ kind: 'download', name: 'tele.zip' });
  });

  it('extracts a chunked ZIP to separate files without overwriting existing files', async () => {
    const saved: Record<string, number[]> = { 'a.csv': [...strToU8('original')] };
    const directory: LocalDirectory = { name: 'exports', async getFileHandle(name, options) {
      if (!options?.create && !(name in saved)) throw new DOMException('absent', 'NotFoundError');
      return { name, async getFile() { return { size: saved[name].length }; }, async createWritable() { saved[name] = []; return new WritableStream({ write(chunk) { saved[name].push(...chunk); } }); } };
    } };
    const zip = zipSync({ 'a.csv': strToU8('id,name\r\n1,中文'), 'b.csv': strToU8('id\r\n') });
    const body = new ReadableStream({ start(controller) { for (let i = 0; i < zip.length; i += 13) controller.enqueue(zip.slice(i, i + 13)); controller.close(); } });
    const files = await saveExport(new Response(body), { kind: 'directory', handle: directory }, vi.fn());
    expect(files.map(file => file.name)).toEqual(['a (1).csv', 'b.csv']);
    expect(new TextDecoder().decode(new Uint8Array(saved['a.csv']))).toBe('original');
    expect(new TextDecoder().decode(new Uint8Array(saved['a (1).csv']))).toBe('id,name\r\n1,中文');
    expect(new TextDecoder().decode(new Uint8Array(saved['b.csv']))).toBe('id\r\n');
  });

  it('rejects path traversal in ZIP entries before creating a file', async () => {
    const getFileHandle = vi.fn();
    const zip = zipSync({ '../private.txt': strToU8('x') });
    await expect(saveExport(new Response(zip), { kind: 'directory', handle: { name: 'exports', getFileHandle } }, vi.fn())).rejects.toThrow('文件名');
    expect(getFileHandle).not.toHaveBeenCalled();
  });

  it('streams ZIP directly into a preselected local file', async () => {
    const chunks: number[] = [];
    const close = vi.fn();
    const handle = { name: 'tele.zip', getFile: async () => ({ size: chunks.length }), createWritable: async () => new WritableStream<Uint8Array>({ write(value) { chunks.push(...value); }, close }) };
    const zip = zipSync({ 'tele.sql': strToU8('SELECT 1;') });
    expect(await saveExport(new Response(zip), { kind: 'zip', handle }, vi.fn())).toEqual([{ name: 'tele.zip', size: zip.length }]);
    expect(chunks).toEqual([...zip]); expect(close).toHaveBeenCalledOnce();
  });

  it.each(['-- plain SQL\nSELECT 1;', '<html>login required</html>', ''])('rejects non-ZIP responses without claiming a local save: %s', async content => {
    const getFileHandle = vi.fn();
    await expect(saveExport(new Response(content), { kind: 'directory', handle: { name: 'exports', getFileHandle } }, vi.fn())).rejects.toThrow();
    expect(getFileHandle).not.toHaveBeenCalled();
  });

  it('rejects an empty ZIP instead of reporting successful extraction', async () => {
    const getFileHandle = vi.fn();
    await expect(saveExport(new Response(zipSync({})), { kind: 'directory', handle: { name: 'exports', getFileHandle } }, vi.fn())).rejects.toThrow();
    expect(getFileHandle).not.toHaveBeenCalled();
  });

  it('aborts a truncated ZIP file save without committing the local file', async () => {
    const close = vi.fn(); const abort = vi.fn();
    const zip = zipSync({ 'tele.sql': strToU8('SELECT 1;') });
    const handle = { name: 'tele.zip', getFile: vi.fn(), createWritable: async () => new WritableStream<Uint8Array>({ write() {}, close, abort }) };
    await expect(saveExport(new Response(zip.slice(0, -10)), { kind: 'zip', handle }, vi.fn())).rejects.toThrow('不完整');
    expect(close).not.toHaveBeenCalled(); expect(abort).toHaveBeenCalledOnce();
    expect(handle.getFile).not.toHaveBeenCalled();
  });

  it('does not report success when local file verification fails', async () => {
    const handle = { name: 'tele.sql', getFile: async () => ({ size: 0 }), createWritable: async () => new WritableStream<Uint8Array>() };
    const directory: LocalDirectory = { name: 'exports', async getFileHandle(_name, options) { if (!options?.create) throw new DOMException('absent', 'NotFoundError'); return handle; } };
    await expect(saveExport(new Response(zipSync({ 'tele.sql': strToU8('SELECT 1;') })), { kind: 'directory', handle: directory }, vi.fn())).rejects.toThrow('大小校验失败');
  });
});
