import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  canUseSimpleHostTerminal,
  findTerminalHostById,
  getSimpleTerminalProtocol,
  openSimpleTerminalPopup,
} from '../simpleHostTerminal';
import type { TerminalGroup, TerminalHost } from '../../types';

afterEach(() => vi.unstubAllGlobals());

function host(overrides: Partial<TerminalHost>): TerminalHost {
  return {
    id: 1,
    name: 'linux-01',
    group: 1,
    privateIp: '10.0.0.1',
    publicIp: '',
    port: 22,
    loginUser: 'root',
    remark: '',
    verified: true,
    ...overrides,
  };
}

describe('simple host terminal helpers', () => {
  it('opens a centered personal terminal popup with its opener detached', () => {
    const popup = { opener: {}, location: { replace: vi.fn() }, focus: vi.fn() };
    const open = vi.fn().mockReturnValue(popup);
    vi.stubGlobal('window', { open, screenX: 20, screenY: 40, outerWidth: 1440, outerHeight: 900 });
    openSimpleTerminalPopup('/host-terminal.html?host=7&container=web', 'container-7-web');
    expect(open).toHaveBeenCalledWith('about:blank', 'container-7-web', 'popup=yes,width=980,height=720,left=250,top=130,resizable=yes,scrollbars=no');
    expect(popup.opener).toBeNull();
    expect(popup.location.replace).toHaveBeenCalledWith('/host-terminal.html?host=7&container=web');
    expect(popup.focus).toHaveBeenCalledOnce();
  });

  it('reports blocked popups instead of falling back to the full terminal', () => {
    vi.stubGlobal('window', { open: vi.fn().mockReturnValue(null), screenX: 0, screenY: 0, outerWidth: 800, outerHeight: 600 });
    expect(() => openSimpleTerminalPopup('/host-terminal.html?host=7', 'container-7')).toThrow('请允许弹窗后重试');
    expect(window.open).toHaveBeenCalledOnce();
    expect(window.open).toHaveBeenCalledWith('about:blank', 'container-7', expect.stringContaining('left=0,top=0'));
  });

  it('requires both host page access and terminal action permission', () => {
    expect(canUseSimpleHostTerminal(['access_hosts', 'action_hosts_terminal'])).toBe(true);
    expect(canUseSimpleHostTerminal(['access_hosts'])).toBe(false);
    expect(canUseSimpleHostTerminal(['action_hosts_terminal'])).toBe(false);
    expect(canUseSimpleHostTerminal([])).toBe(false);
  });

  it('finds a host in nested terminal groups by id', () => {
    const nested = host({ id: 42, name: 'nested' });
    const groups: TerminalGroup[] = [
      { id: 1, name: 'root', hosts: [host({ id: 1 })], children: [{ id: 2, name: 'child', hosts: [nested], children: [] }] },
    ];

    expect(findTerminalHostById(groups, 42)).toEqual(nested);
    expect(findTerminalHostById(groups, 404)).toBeNull();
  });

  it('selects RDP for explicit RDP and Windows hosts, otherwise SSH', () => {
    expect(getSimpleTerminalProtocol(host({ terminalProtocol: 'rdp' }))).toBe('rdp');
    expect(getSimpleTerminalProtocol(host({ platformType: 'windows' }))).toBe('rdp');
    expect(getSimpleTerminalProtocol(host({ os: 'windows' }))).toBe('rdp');
    expect(getSimpleTerminalProtocol(host({ terminalProtocol: 'ssh', platformType: 'linux' }))).toBe('ssh');
  });
});
