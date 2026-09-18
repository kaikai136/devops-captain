import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { parse as parseSfc } from '@vue/compiler-sfc';

function readSource(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(`../${relativePath}`, import.meta.url)), 'utf8');
}

function template(relativePath: string) {
  return parseSfc(readSource(relativePath), { filename: relativePath }).descriptor.template?.content ?? '';
}

describe('Element Plus migration contract', () => {
  it('wires Element Plus into the standalone terminal entries', () => {
    const terminal = readSource('terminal.ts');
    const hostTerminal = readSource('host-terminal.ts');

    for (const source of [terminal, hostTerminal]) {
      expect(source).toContain("import 'element-plus/dist/index.css';");
      expect(source).toContain("import zhCn from 'element-plus/es/locale/lang/zh-cn';");
      expect(source).toContain('app.use(ElementPlus, { locale: zhCn })');
    }
    expect(terminal).toContain('createApp(WebTerminalPage)');
    expect(hostTerminal).toContain('createApp(SimpleHostTerminalPage)');
  });

  it('bridges Element Plus tokens to the brand palette', () => {
    const theme = readSource('styles/base/element-plus-theme.css');
    expect(theme).toContain('--el-color-primary');
    expect(theme).toContain('--el-border-radius-base');
    expect(theme).toContain('html.dark');
  });

  it('keeps global base control styles away from Element Plus internals', () => {
    const controls = readSource('styles/base/controls.css');

    expect(controls).toContain('input:not(.el-input__inner)');
    expect(controls).toContain('textarea:not(.el-textarea__inner)');
    expect(controls).toContain('button:not(.el-button)');
  });

  it('keeps Element Plus dialogs vertically balanced with a scrollable body', () => {
    const theme = readSource('styles/base/element-plus-overrides.css');

    expect(theme).toContain('.el-dialog');
    expect(theme).toContain('.el-dialog__body');
    expect(theme).toContain('flex-direction: column');
    expect(theme).toContain('overflow: auto');
    expect(theme).toContain('.el-dialog__footer');
  });

  it('loads the shared Element Plus override sheet in every app entry', () => {
    const appStyles = readSource('styles.css');
    const terminal = readSource('terminal.ts');
    const hostTerminal = readSource('host-terminal.ts');

    expect(appStyles).toContain('./styles/base/element-plus-overrides.css');
    expect(terminal).toContain('./styles/base/element-plus-overrides.css');
    expect(hostTerminal).toContain('./styles/base/element-plus-overrides.css');
  });

  it('routes feedback through Element Plus message primitives', () => {
    const feedback = readSource('composables/app/useFeedback.ts');
    expect(feedback).toContain('ElMessage');
    expect(feedback).toContain('ElMessageBox');
    expect(feedback).not.toContain('confirmDialog');
    expect(feedback).not.toContain('scopedToastVisible');
  });

  it('keeps host and terminal surfaces on Element Plus visible controls', () => {
    const componentPaths = [
      'features/hosts/components/CredentialSelector.vue',
      'features/hosts/components/HostEditorDialog.vue',
      'features/hosts/components/HostExportDialog.vue',
      'features/hosts/components/HostGroupTree.vue',
      'features/hosts/components/HostImportDialog.vue',
      'features/hosts/components/HostManager.vue',
      'features/hosts/components/HostMoveDialog.vue',
      'features/hosts/components/HostTable.vue',
      'features/hosts/components/HostToolbar.vue',
      'components/terminal/SimpleHostTerminalPage.vue',
      'components/terminal/WebTerminalPage.vue',
      'features/terminal/components/files/FileCreateDialog.vue',
      'features/terminal/components/files/FileDownloadDialog.vue',
      'features/terminal/components/files/FilePropertiesDialog.vue',
      'features/terminal/components/files/FileTable.vue',
      'features/terminal/components/files/FileToolbar.vue',
      'features/terminal/components/files/FileUploadDialog.vue',
      'features/terminal/components/files/SftpPanel.vue',
      'shared/components/LockScreenOverlay.vue',
      'components/tools/SystemSettingsPanel.vue',
    ];

    for (const path of componentPaths) {
      const source = template(path);
      const hiddenInputsRemoved = source.replace(/<input[^>]*hidden[^>]*\/?>/g, '').trim();
      if (hiddenInputsRemoved) expect(source, path).toContain('<el-');
      expect(source, path).not.toMatch(/<(button|select|option|textarea|table)\b/);
      expect(source, path).not.toMatch(/<input(?![^>]*hidden)/);
    }
  });
});
