import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function source() {
  return readFileSync(fileURLToPath(new URL('../SimpleHostTerminalPage.vue', import.meta.url)), 'utf8');
}

describe('SimpleHostTerminalPage structure', () => {
  it('checks current user terminal permission before loading and connecting a host', () => {
    const script = parseSfc(source(), { filename: 'SimpleHostTerminalPage.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toMatch(/const current = await getCurrentUser\(\)/);
    expect(script).toMatch(/if \(!canUseSimpleHostTerminal\(current\.user\.featurePermissionCodes\)\) \{/);
    expect(script).toMatch(/status\.value = 'denied'/);
    expect(script).toMatch(/return;\s*\}\s*const groups = await listTerminalTree\(\)/);
  });

  it('uses existing SSH and RDP protocol helpers for the standalone host terminal', () => {
    const script = parseSfc(source(), { filename: 'SimpleHostTerminalPage.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain('buildTerminalWebSocketUrl');
    expect(script).toContain('buildRdpWebSocketUrl');
    expect(script).toContain('buildRdpConnectionQuery');
    expect(script).toContain('getSimpleTerminalProtocol');
  });

  it('reuses full terminal black-screen helpers for SSH terminal behavior', () => {
    const script = parseSfc(source(), { filename: 'SimpleHostTerminalPage.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain('SearchAddon');
    expect(script).toContain('createTerminalScreenOptions(readTerminalFontSize(), terminalSettings.value.scrollbackLines)');
    expect(script).toContain('attachTerminalPasteHandler');
    expect(script).toContain('normalizeTerminalPasteText');
    expect(script).toContain('handleTerminalCopyShortcut');
    expect(script).toContain('writeTextToClipboard');
    expect(script).toContain('getSendableTerminalData');
    expect(script).toContain('collectTerminalSearchMatches');
    expect(script).toContain('selectTerminalSearchMatch');
    expect(script).toContain('getTerminalVisibleText');
  });

  it('adds only terminal-screen search and context menu controls to the standalone shell', () => {
    const template = parseSfc(source(), { filename: 'SimpleHostTerminalPage.vue' }).descriptor.template?.content ?? '';

    expect(template).toContain('simple-host-terminal-search');
    expect(template).toContain('<AppContextMenu');
    expect(template).toContain(':items="terminalContextMenuItems"');
    expect(template).toContain('@select="runContextMenuItem"');
    expect(template).toContain('@contextmenu="openSshContextMenu($event)"');
  });

  it('delegates submenu placement and overflow to the shared menu primitives', () => {
    const { descriptor } = parseSfc(source());
    expect(descriptor.template?.content).not.toContain('simple-host-terminal-context-submenu');
    expect(descriptor.scriptSetup?.content).not.toContain('isContextSubmenuLeft');
    expect(descriptor.scriptSetup?.content).not.toContain('SIMPLE_TERMINAL_CONTEXT_MENU_HEIGHT');
  });

  it('actively syncs SSH terminal size after standalone fits', () => {
    const script = parseSfc(source(), { filename: 'SimpleHostTerminalPage.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain('sendActiveSshResize');
    expect(script).toMatch(/fitAddon\?\.fit\(\);\s*sendActiveSshResize\(\)/);
    expect(script).toContain("sshSocket.send(JSON.stringify({ type: 'resize', cols: xterm.cols, rows: xterm.rows }))");
  });
});
