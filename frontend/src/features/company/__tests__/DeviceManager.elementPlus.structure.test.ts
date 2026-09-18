import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function componentSource() {
  return readFileSync(fileURLToPath(new URL('../components/DeviceManager.vue', import.meta.url)), 'utf8');
}

describe('DeviceManager Element Plus migration', () => {
  it('replaces the native table, dialog, and pagination with Element Plus components', () => {
    const template = parseSfc(componentSource(), { filename: 'DeviceManager.vue' }).descriptor.template?.content ?? '';

    expect(template).toContain('<el-table');
    expect(template).toContain('<el-table-column');
    expect(template).toContain('type="selection"');
    expect(template).toContain('<el-tag');
    expect(template).toContain('<el-dialog');
    expect(template).toContain('<el-form');
    expect(template).toContain('<el-form-item');
    expect(template).toContain('<AppPagination');
    expect(template).toContain('<el-button');
    expect(template).toContain('<el-input');
    expect(template).toContain('<el-select');
    expect(template).toContain('<el-date-picker');

    expect(template).not.toContain('<table');
    expect(template).not.toContain('<input');
    expect(template).not.toContain('<select');
    expect(template).not.toContain('<option');
    expect(template).not.toContain('<textarea');
    expect(template).not.toContain('modal-backdrop');
  });

  it('drives selection through el-table selection-change', () => {
    const script = parseSfc(componentSource(), { filename: 'DeviceManager.vue' }).descriptor.scriptSetup?.content ?? '';

    expect(script).toContain('function handleSelectionChange(rows: CompanyDevice[])');
    expect(script).toContain('selectedDevices.value = rows');
    expect(script).not.toContain('selectedIds');
    expect(script).not.toContain('toggleAll');
    expect(script).not.toContain('toggleDevice');
  });
});
