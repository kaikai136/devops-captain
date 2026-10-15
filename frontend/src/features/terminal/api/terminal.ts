import { AUTH_EXPIRED_EVENT, ApiUnauthorizedError, apiDelete, apiGet, apiPost, apiPostForm, apiPut } from '../../../api';
import type {
  TerminalDownloadProtocol,
  TerminalFileAuditListResponse,
  TerminalFileListResponse,
  TerminalFileProperties,
  TerminalGroup,
  TerminalMonitorResponse,
  TerminalQuickCommand,
  SshGatewayConnectionInfo,
} from '../types';

const terminalBaseUrl = '/api/web-terminal';

export function listTerminalTree() {
  return apiGet<TerminalGroup[]>(`${terminalBaseUrl}/tree/`);
}

export function getSshGatewayConnectionInfo(hostId?: number) {
  const query = hostId ? `?${new URLSearchParams({ host: String(hostId) }).toString()}` : '';
  return apiGet<SshGatewayConnectionInfo>(`${terminalBaseUrl}/ssh-gateway/connection-info/${query}`);
}

export function listTerminalFileAudits(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(key, String(value));
  }
  const suffix = query.toString() ? `?${query.toString()}` : '';
  return apiGet<TerminalFileAuditListResponse>(`${terminalBaseUrl}/file-audits/${suffix}`);
}

export function listTerminalQuickCommands() {
  return apiGet<TerminalQuickCommand[]>(`${terminalBaseUrl}/quick-commands/`);
}

export function createTerminalQuickCommand(payload: unknown) {
  return apiPost<TerminalQuickCommand>(`${terminalBaseUrl}/quick-commands/`, payload);
}

export function updateTerminalQuickCommand(commandId: number, payload: unknown) {
  return apiPut<TerminalQuickCommand>(`${terminalBaseUrl}/quick-commands/${commandId}/`, payload);
}

export function removeTerminalQuickCommand(commandId: number) {
  return apiDelete<{ deleted: boolean }>(`${terminalBaseUrl}/quick-commands/${commandId}/`);
}

export function reorderTerminalQuickCommands(ids: number[]) {
  return apiPost<TerminalQuickCommand[]>(`${terminalBaseUrl}/quick-commands/reorder/`, { ids });
}

export function listTerminalFiles(hostId: number, payload: unknown, options: RequestInit = {}) {
  return apiPost<TerminalFileListResponse>(`${terminalBaseUrl}/hosts/${hostId}/files/list/`, payload, options);
}

export function listTerminalDownloadFiles(hostId: number, payload: unknown, options: RequestInit = {}) {
  return apiPost<TerminalFileListResponse>(`${terminalBaseUrl}/hosts/${hostId}/files/list-download/`, payload, options);
}

export function uploadTerminalFile(
  hostId: number,
  payload: { directory: string; filename: string; relativePath: string; file: File },
  options: RequestInit = {},
) {
  const body = new FormData();
  body.set('directory', payload.directory);
  body.set('filename', payload.filename);
  body.set('relativePath', payload.relativePath);
  body.set('file', payload.file, payload.filename || payload.file.name);
  return apiPostForm<{ protocol: string; size?: number; path?: string }>(
    `${terminalBaseUrl}/hosts/${hostId}/files/upload/`, body, options,
  );
}

export function createTerminalFileEntry(hostId: number, endpoint: string, payload: unknown) {
  return apiPost<TerminalFileProperties>(`${terminalBaseUrl}/hosts/${hostId}/files/${endpoint}/`, payload);
}

export function deleteTerminalFileEntry(hostId: number, payload: unknown) {
  return apiPost<{ deleted: boolean }>(`${terminalBaseUrl}/hosts/${hostId}/files/delete/`, payload);
}

export function renameTerminalFileEntry(hostId: number, payload: unknown) {
  return apiPost<TerminalFileProperties>(`${terminalBaseUrl}/hosts/${hostId}/files/rename/`, payload);
}

export function getTerminalFileProperties(hostId: number, path: string) {
  return apiPost<TerminalFileProperties>(`${terminalBaseUrl}/hosts/${hostId}/files/properties/`, { path });
}

export function updateTerminalFileProperties(hostId: number, payload: unknown) {
  return apiPost<TerminalFileProperties>(`${terminalBaseUrl}/hosts/${hostId}/files/properties/update/`, payload);
}

export function getTerminalMonitor(hostId: number) {
  return apiPost<TerminalMonitorResponse>(`${terminalBaseUrl}/hosts/${hostId}/monitor/`, {});
}

export function buildTerminalFileDownloadRawUrl(hostId: number, path: string, protocol: TerminalDownloadProtocol) {
  const params = new URLSearchParams({ path, protocol });
  return `${terminalBaseUrl}/hosts/${hostId}/files/download/raw/?${params.toString()}`;
}

export interface TerminalFileContentResponse {
  path: string;
  filename: string;
  size: number;
  isText: boolean;
  contentType: string;
  content: string | null;
  blob: Blob;
}

export function getTerminalFileContent(hostId: number, path: string, options: RequestInit = {}) {
  const query = new URLSearchParams({ path });
  return fetch(`${terminalBaseUrl}/hosts/${hostId}/files/content/?${query.toString()}`, { credentials: 'include', ...options })
    .then(async (response) => {
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { error?: string; detail?: string } | null;
        const message = payload?.error || payload?.detail || '读取文件失败';
        if (response.status === 401) {
          window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
          throw new ApiUnauthorizedError(message);
        }
        throw new Error(message);
      }
      const blob = await response.blob();
      const contentType = response.headers.get('content-type') || 'application/octet-stream';
      const encodedFilename = response.headers.get('content-disposition')?.match(/filename\*=UTF-8''([^;]+)/)?.[1];
      let filename = path.split('/').pop() || 'file';
      if (encodedFilename) {
        try { filename = decodeURIComponent(encodedFilename); } catch { /* Keep the original path name. */ }
      }
      let content: string | null = null;
      if (!contentType.startsWith('image/')) {
        try {
          const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await blob.arrayBuffer());
          if (!/[\u0000-\u0008\u000e-\u001f]/.test(text)) content = text;
        } catch {
          // Non-UTF-8 files are sent to the image preview or download fallback.
        }
      }
      return {
        path, filename, size: blob.size, isText: content !== null,
        contentType, content, blob,
      };
    });
}

export function updateTerminalFileContent(hostId: number, path: string, content: string) {
  const body = new FormData();
  body.set('path', path);
  body.set('file', new Blob([content], { type: 'text/plain;charset=utf-8' }), path.split('/').pop() || 'file');
  return apiPostForm<{ path: string; size: number; protocol?: string }>(
    `${terminalBaseUrl}/hosts/${hostId}/files/content/update/`, body,
  );
}
