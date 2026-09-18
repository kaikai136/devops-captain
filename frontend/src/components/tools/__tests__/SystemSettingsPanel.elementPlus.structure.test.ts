import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function panelSource() {
  return readFileSync(fileURLToPath(new URL('../SystemSettingsPanel.vue', import.meta.url)), 'utf8');
}

describe('SystemSettingsPanel Element Plus migration', () => {
  it('replaces native form controls with Element Plus components', () => {
    const template = parseSfc(panelSource(), { filename: 'SystemSettingsPanel.vue' }).descriptor.template?.content ?? '';

    expect(template).toContain('<el-button');
    expect(template).toContain('<el-input');
    expect(template).toContain('<el-input-number');
    expect(template).toContain('<el-select');
    expect(template).toContain('<el-option');
    expect(template).toContain('<el-checkbox');
    expect(template).toContain('<el-color-picker');

    expect(template).not.toContain('<input');
    expect(template).not.toContain('<select');
    expect(template).not.toContain('<option');
    expect(template).not.toContain('<textarea');
  });

  it('uses el-button with type primary for the save action', () => {
    const template = parseSfc(panelSource(), { filename: 'SystemSettingsPanel.vue' }).descriptor.template?.content ?? '';

    expect(template).toContain('type="primary"');
    expect(template).toContain('@click="saveCurrentTab"');
  });

  it('provides global theme presets, custom HEX input, and light/dark previews', () => {
    const source = panelSource();
    const template = parseSfc(source, { filename: 'SystemSettingsPanel.vue' }).descriptor.template?.content ?? '';

    expect(source).toContain('uiThemePresetOptions');
    expect(source).toContain('saveUiThemeSetting');
    expect(template).toContain('class="theme-preset-grid"');
    expect(template).toContain('v-model="uiThemeDraft.customPrimary"');
    expect(template).toContain('class="theme-preview theme-preview-light"');
    expect(template).toContain('class="theme-preview theme-preview-dark"');
  });
});
