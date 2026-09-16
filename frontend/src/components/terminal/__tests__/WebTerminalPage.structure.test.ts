import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function source() {
  return readFileSync(fileURLToPath(new URL('../WebTerminalPage.vue', import.meta.url)), 'utf8');
}

describe('WebTerminalPage structure', () => {
  it('writes live SSH output to xterm without rewriting terminal control streams', () => {
    const script = parseSfc(source(), { filename: 'WebTerminalPage.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain("tab.terminal.write(message.data ?? '')");
    expect(script).not.toContain('tab.terminal.write(highlightTerminalOutput');
  });

  it('normalizes pasted shell command snippets before sending them to terminals', () => {
    const script = parseSfc(source(), { filename: 'WebTerminalPage.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain('normalizeTerminalPasteText');
  });

  it('keeps Element Plus tree row content in the row flex layout', () => {
    const styles = readFileSync(fileURLToPath(new URL('../../../styles/terminal.css', import.meta.url)), 'utf8').replace(/\r\n/g, '\n');

    expect(styles).toContain('.terminal-tree-row > span {\n  display: contents;\n}');
    expect(styles).toContain('.terminal-tree-row > span > span {');
    expect(styles).not.toContain('.terminal-tree-row span {');
  });

  it('keeps the vertical terminal sidebar rail buttons aligned', () => {
    const styles = readFileSync(fileURLToPath(new URL('../../../styles/terminal.css', import.meta.url)), 'utf8').replace(/\r\n/g, '\n');

    expect(styles).toContain('.terminal-side-switch .el-button + .el-button {\n  margin-left: 0;\n}');
  });

  it('keeps compact tab labels and trailing controls in the same grid', () => {
    const styles = readFileSync(fileURLToPath(new URL('../../../styles/terminal.css', import.meta.url)), 'utf8').replace(/\r\n/g, '\n');
    const tabRule = styles.match(/\.terminal-tabs button \{([^}]+)\}/)?.[1] ?? '';

    expect(styles).toContain('.terminal-tabs button > span {\n  display: contents;\n}');
    expect(styles).toContain('.terminal-tabs .el-button + .el-button {\n  margin-left: 0;\n}');
    expect(tabRule).toContain('grid-template-columns: minmax(0, 1fr) 8px 20px;');
    expect(tabRule).toContain('flex: 0 0 clamp(104px, 8vw, 136px);');
    expect(tabRule).toContain('text-align: left;');
    expect(styles).toContain('grid-template-columns: minmax(0, 1fr) 17px 8px 20px;');
  });

  it('keeps host status pinned to the resizable tree edge without row offsets', () => {
    const styles = readFileSync(fileURLToPath(new URL('../../../styles/terminal.css', import.meta.url)), 'utf8').replace(/\r\n/g, '\n');
    const rowRule = styles.match(/\.terminal-tree-row \{([^}]+)\}/)?.[1] ?? '';
    const statusRule = styles.match(/\.terminal-host-verify-dot \{([^}]+)\}/)?.[1] ?? '';

    expect(rowRule).toContain('width: 100%;');
    expect(rowRule).toContain('min-width: 0;');
    expect(styles).toContain('.terminal-tree-row + .terminal-tree-row {\n  margin-left: 0;\n}');
    expect(statusRule).toContain('margin-left: auto;');
    expect(statusRule).toContain('flex: 0 0 auto;');
  });

  it('shares accessible context menus between screen and tabs without legacy positioning', () => {
    const { descriptor } = parseSfc(source());
    const template = descriptor.template?.content ?? '';
    const script = descriptor.scriptSetup?.content ?? '';

    expect(template.match(/<AppContextMenu/g)).toHaveLength(2);
    expect(template).toContain(':items="terminalContextMenuItems"');
    expect(template).toContain(':items="terminalTabContextMenuItems"');
    expect(template).toContain('@select="runTerminalContextMenuItem"');
    expect(template).toContain('@select="runTerminalTabContextMenuItem"');
    expect(template).not.toContain('terminal-file-context-submenu');
    expect(script).not.toContain('isTerminalContextSubmenuLeft');
    expect(script).not.toContain('TERMINAL_CONTEXT_MENU_HEIGHT');
  });
});
