import { Unzip, UnzipInflate } from 'fflate';
export function destinationMode() {
    const host = window;
    return host.showDirectoryPicker ? 'directory' : host.showSaveFilePicker ? 'zip' : 'download';
}
export async function chooseExportDestination(name) {
    const host = window;
    if (host.showDirectoryPicker)
        return { kind: 'directory', handle: await host.showDirectoryPicker({ mode: 'readwrite' }) };
    if (host.showSaveFilePicker)
        return { kind: 'zip', handle: await host.showSaveFilePicker({ suggestedName: name, types: [{ description: 'ZIP 压缩文件', accept: { 'application/zip': ['.zip'] } }] }) };
    // Browsers without File System Access cannot choose a path before download.
    return { kind: 'download', name };
}
export function validExportFileName(name) {
    return Boolean(name && name !== '.' && name !== '..' && !/[\\/:\x00-\x1f]/.test(name));
}
async function unusedFile(directory, name) {
    const dot = name.lastIndexOf('.');
    const base = dot > 0 ? name.slice(0, dot) : name;
    const extension = dot > 0 ? name.slice(dot) : '';
    for (let index = 0; index < 10000; index++) {
        const candidate = index ? `${base} (${index})${extension}` : name;
        try {
            await directory.getFileHandle(candidate);
        }
        catch (error) {
            if (error.name !== 'NotFoundError')
                throw error;
            return directory.getFileHandle(candidate, { create: true });
        }
    }
    throw new Error('目标目录同名文件过多，请选择其他目录');
}
// fflate accepts streams without ZIP entries, so successful parsing alone is not proof of a ZIP.
function zipValidator() {
    let size = 0;
    let prefix = new Uint8Array();
    let tail = new Uint8Array();
    return new TransformStream({
        transform(chunk, controller) {
            size += chunk.length;
            if (prefix.length < 4) {
                const next = new Uint8Array(Math.min(4, prefix.length + chunk.length));
                next.set(prefix);
                next.set(chunk.subarray(0, next.length - prefix.length), prefix.length);
                prefix = next;
                if (prefix.length === 4 && (prefix[0] !== 0x50 || prefix[1] !== 0x4b || prefix[2] !== 3 || prefix[3] !== 4)) {
                    throw new Error('服务器返回的不是有效 ZIP 导出包，请重启后端及导出任务服务后重新导出');
                }
            }
            const next = new Uint8Array(Math.min(65557, tail.length + chunk.length));
            const retained = Math.max(0, next.length - chunk.length);
            if (retained)
                next.set(tail.subarray(tail.length - retained));
            next.set(chunk.subarray(Math.max(0, chunk.length - next.length)), retained);
            tail = next;
            controller.enqueue(chunk);
        },
        flush() {
            for (let offset = tail.length - 22; offset >= 0; offset--) {
                if (tail[offset] !== 0x50 || tail[offset + 1] !== 0x4b || tail[offset + 2] !== 5 || tail[offset + 3] !== 6)
                    continue;
                const view = new DataView(tail.buffer, tail.byteOffset + offset, tail.length - offset);
                if (offset + 22 + view.getUint16(20, true) === tail.length && view.getUint16(10, true) > 0 && size > 22)
                    return;
            }
            throw new Error('导出包为空或下载不完整，未确认保存成功，请重新保存');
        },
    });
}
export async function saveExport(response, destination, onFile, signal) {
    if (!response.ok)
        throw new Error('下载导出文件失败，请检查权限或重试');
    if (!response.body)
        throw new Error('浏览器不支持流式下载');
    if (destination.kind === 'download') {
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a');
        link.href = url;
        link.download = destination.name;
        link.click();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
        return [];
    }
    const body = response.body.pipeThrough(zipValidator());
    if (destination.kind === 'zip') {
        let size = 0;
        const writable = await destination.handle.createWritable();
        await body.pipeThrough(new TransformStream({ transform(chunk, controller) { size += chunk.length; controller.enqueue(chunk); } })).pipeTo(writable, { signal });
        if ((await destination.handle.getFile()).size !== size)
            throw new Error('本地 ZIP 文件大小校验失败，请重新保存');
        onFile(destination.handle.name);
        return [{ name: destination.handle.name, size }];
    }
    const reader = body.getReader();
    let pending = Promise.resolve();
    let failure;
    const streams = new Set();
    const saved = [];
    const queue = (action) => {
        pending = pending.then(async () => { if (failure)
            return; try {
            await action();
        }
        catch (error) {
            failure = error;
        } });
    };
    const unzip = new Unzip(file => {
        if (!validExportFileName(file.name)) {
            failure = new Error('导出文件名不安全');
            file.terminate();
            return;
        }
        let writer;
        let handle;
        let size = 0;
        queue(async () => {
            handle = await unusedFile(destination.handle, file.name);
            writer = (await handle.createWritable()).getWriter();
            streams.add(writer);
            onFile(handle.name);
        });
        file.ondata = (error, data, final) => {
            if (error) {
                failure = error;
                return;
            }
            queue(async () => {
                if (signal?.aborted)
                    throw new DOMException('已取消本地保存', 'AbortError');
                if (data.length) {
                    await writer.write(data);
                    size += data.length;
                }
                if (final) {
                    await writer.close();
                    streams.delete(writer);
                    if ((await handle.getFile()).size !== size)
                        throw new Error(`本地文件 ${handle.name} 大小校验失败，请重新保存`);
                    saved.push({ name: handle.name, size });
                }
            });
        };
        file.start();
    });
    unzip.register(UnzipInflate);
    try {
        while (true) {
            if (signal?.aborted)
                throw new DOMException('已取消本地保存', 'AbortError');
            const { done, value } = await reader.read();
            if (done) {
                unzip.push(new Uint8Array(), true);
                await pending;
                break;
            }
            // Bound decompression and disk writes to a small compressed chunk.
            for (let offset = 0; offset < value.length; offset += 16384) {
                unzip.push(value.subarray(offset, offset + 16384));
                await pending;
                if (failure)
                    throw failure;
            }
        }
        if (failure)
            throw failure;
        if (streams.size)
            throw new Error('导出文件下载不完整，请重新保存');
        if (!saved.length)
            throw new Error('导出包中没有文件，未写入本地，请重新导出');
        return saved;
    }
    catch (error) {
        await reader.cancel().catch(() => undefined);
        await Promise.allSettled([...streams].map(writer => writer.abort()));
        throw error;
    }
    finally {
        reader.releaseLock();
    }
}
