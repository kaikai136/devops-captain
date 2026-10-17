import type { TerminalGroup, TerminalHost, TerminalTabKind } from '../types';

const HOST_ACCESS_PERMISSION = 'access_hosts';
const HOST_TERMINAL_PERMISSION = 'action_hosts_terminal';

export function openSimpleTerminalPopup(url: string, targetName: string) {
  const width = 980;
  const height = 720;
  const left = Math.max(0, Math.round(window.screenX + (window.outerWidth - width) / 2));
  const top = Math.max(0, Math.round(window.screenY + (window.outerHeight - height) / 2));
  const features = [
    'popup=yes', `width=${width}`, `height=${height}`,
    `left=${left}`, `top=${top}`, 'resizable=yes', 'scrollbars=no',
  ].join(',');
  const popup = window.open('about:blank', targetName, features);
  if (!popup) throw new Error('浏览器阻止了终端弹窗，请允许弹窗后重试。');
  popup.opener = null;
  popup.location.replace(url);
  popup.focus();
}

export function canUseSimpleHostTerminal(permissionCodes: readonly string[] | Set<string> | undefined | null) {
  const codes = permissionCodes instanceof Set ? permissionCodes : new Set(permissionCodes ?? []);
  return codes.has(HOST_ACCESS_PERMISSION) && codes.has(HOST_TERMINAL_PERMISSION);
}

export function findTerminalHostById(groups: readonly TerminalGroup[], hostId: number): TerminalHost | null {
  for (const group of groups) {
    const host = group.hosts.find((item) => item.id === hostId);
    if (host) return host;
    const childHost = findTerminalHostById(group.children, hostId);
    if (childHost) return childHost;
  }
  return null;
}

export function getSimpleTerminalProtocol(host: TerminalHost): TerminalTabKind {
  const protocol = String(host.terminalProtocol || '').toLowerCase();
  const platform = String(host.platformType || host.os || '').toLowerCase();
  return protocol === 'rdp' || platform === 'windows' ? 'rdp' : 'ssh';
}
