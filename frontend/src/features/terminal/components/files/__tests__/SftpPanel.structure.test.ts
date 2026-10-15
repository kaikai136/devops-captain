import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const panel = readFileSync(new URL('../SftpPanel.vue', import.meta.url), 'utf8');
const workspace = readFileSync(new URL('../TerminalFileWorkspace.vue', import.meta.url), 'utf8');

describe('file context actions', () => {
  it('exposes open, preview, and CodeMirror editor actions', () => {
    expect(panel).toContain("id: 'open'");
    expect(panel).toContain("id: 'preview'");
    expect(panel).toContain("id: 'edit'");
    expect(panel).toContain("emit('openFile'");
  });

  it('keeps editor affordances and save shortcut in the workspace', () => {
    expect(workspace).toContain("key: 'Mod-s'");
    expect(workspace).toContain('使用内置编辑器打开');
    expect(workspace).toContain('lineNumbers()');
    expect(workspace).toContain('searchKeymap');
  });
});
