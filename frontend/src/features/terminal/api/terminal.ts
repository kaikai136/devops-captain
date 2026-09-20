import { apiDelete, apiGet, apiPost, apiPostForm, apiPut } from '../../../api';
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
