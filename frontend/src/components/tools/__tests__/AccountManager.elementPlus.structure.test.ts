import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function panelSource() {
  return readFileSync(fileURLToPath(new URL('../AccountManager.vue', import.meta.url)), 'utf8');
}

describe('AccountManager Element Plus migration', () => {
  it('replaces the native table, dialog, and controls with Element Plus components', () => {
    const template = parseSfc(panelSource(), { filename: 'AccountManager.vue' }).descriptor.template?.content ?? '';

    expect(template).toContain('<el-table');
    expect(template).toContain('<el-table-column');
    expect(template).toContain('<el-tag');
    expect(template).toContain('<el-dialog');
    expect(template).toContain('<el-form');
    expect(template).toContain('<el-form-item');
    expect(template).toContain('<el-button');
    expect(template).toContain('<el-input');
    expect(template).toContain('<el-upload');

    expect(template).not.toContain('<table');
    expect(template).not.toContain('<input');
    expect(template).not.toContain('<select');
    expect(template).not.toContain('<option');
    expect(template).not.toContain('<textarea');
    expect(template).not.toContain('modal-backdrop');
  });

  it('drives the private key upload through el-upload raw file', () => {
    const script = parseSfc(panelSource(), { filename: 'AccountManager.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain('function uploadPrivateKey(uploadFile: { raw?: File })');
    expect(script).not.toContain('uploadPrivateKey(event: Event)');
  });

  it('gives the account popup a dedicated responsive form layout and visible input borders', () => {
    const template = parseSfc(panelSource(), { filename: 'AccountManager.vue' }).descriptor.template?.content ?? '';
    const styles = readFileSync(fileURLToPath(new URL('../../../styles/tools/account-manager.css', import.meta.url)), 'utf8');

    expect(template).toContain('account-popup-form');
    expect(styles).toContain('.account-popup-dialog .account-popup-form');
    expect(styles).toContain('grid-template-columns: repeat(2, minmax(0, 1fr))');
    expect(styles).toContain('box-shadow: 0 0 0 1px var(--el-border-color, #d6e3f4) inset');
    expect(styles).toContain('@media (max-width: 640px)');
  });
});
