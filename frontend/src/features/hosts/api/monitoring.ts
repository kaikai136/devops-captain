import { apiPost } from '../../../api';
import { getTerminalMonitor } from '../../terminal/api/terminal';

export interface HostContainer {
  id: string;
  name: string;
  image: string;
  command: string;
  status: string;
  state: 'running' | 'paused' | 'exited' | 'created' | 'unknown';
  uptime: string;
  ports: string;
  cpuPercent: number | null;
  memoryUsageBytes: number | null;
  memoryLimitBytes: number | null;
  memoryPercent: number | null;
}

export type ContainerAction = 'start' | 'stop' | 'restart';
export interface HostContainers { available: boolean; containers: HostContainer[]; reason?: string }
export interface DockerImage {
  id: string;
  repositories: string[];
  tags: string[];
  references?: string[];
  createdAt: string;
  size: string;
  diskUsage?: string;
  contentSize?: string;
  extra?: string;
}
export interface DockerImages { available: boolean; images: DockerImage[]; total: number; reason?: string }
export interface DockerNetworks { available: boolean; networks: Array<{ id: string; name: string; driver: string; scope: string }>; total: number; reason?: string }
export interface DockerVolumes { available: boolean; volumes: Array<{ name: string; driver: string }>; total: number; reason?: string }

const base = (hostId: number) => `/api/web-terminal/hosts/${hostId}`;
export const getHostMonitor = getTerminalMonitor;
export function getHostContainers(hostId: number, options: RequestInit = {}) {
  return apiPost<HostContainers>(`${base(hostId)}/containers/`, {}, options);
}
export function getDockerImages(hostId: number, options: RequestInit = {}) { return apiPost<DockerImages>(`${base(hostId)}/images/`, {}, options); }
export function getDockerNetworks(hostId: number, options: RequestInit = {}) { return apiPost<DockerNetworks>(`${base(hostId)}/networks/`, {}, options); }
export function getDockerVolumes(hostId: number, options: RequestInit = {}) { return apiPost<DockerVolumes>(`${base(hostId)}/volumes/`, {}, options); }
export function controlHostContainer(hostId: number, containerId: string, action: ContainerAction) {
  return apiPost<{ success: boolean }>(`${base(hostId)}/containers/action/`, { containerId, action });
}
export function getHostContainerLogs(hostId: number, containerId: string, tail = 200, options: RequestInit = {}) {
  return apiPost<{ logs: string; truncated: boolean }>(`${base(hostId)}/containers/logs/`, { containerId, tail }, options);
}

export function containerTerminalUrl(hostId: number, containerId: string) {
  return `/host-terminal.html?${new URLSearchParams({ host: String(hostId), container: containerId })}`;
}

export function appendContainerToSocketUrl(url: string, hostId: number, search: string) {
  const query = new URLSearchParams(search);
  const container = query.get('container');
  if (!container || Number(query.get('host')) !== hostId) return url;
  return `${url}${url.includes('?') ? '&' : '?'}${new URLSearchParams({ container })}`;
}
