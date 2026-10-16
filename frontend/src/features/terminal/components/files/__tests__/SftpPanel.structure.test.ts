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

  it('offers three conflict actions and guards dismissal while busy', () => {
    expect(workspace).toContain('title="文件已变更"');
    expect(workspace).toContain('active && tab.conflict');
    expect(workspace).toContain("emit('cancelConflict')");
    expect(workspace).toContain("emit('reloadConflict')");
    expect(workspace).toContain("emit('forceSave')");
    expect(workspace).toContain(':close-on-press-escape="!tab.loading && !tab.saving"');
    expect(workspace).toContain(':close-on-click-modal="false"');
    expect(workspace.indexOf('>取消</el-button>')).toBeLessThan(workspace.indexOf('>放弃并重新加载</el-button>'));
    expect(workspace.indexOf('>放弃并重新加载</el-button>')).toBeLessThan(workspace.indexOf('>强制保存</el-button>'));
  });
});
