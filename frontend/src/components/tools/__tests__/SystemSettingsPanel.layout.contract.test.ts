import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function panelParts() {
  const source = readFileSync(fileURLToPath(new URL('../SystemSettingsPanel.vue', import.meta.url)), 'utf8');
  const descriptor = parseSfc(source, { filename: 'SystemSettingsPanel.vue' }).descriptor;
  return { script: descriptor.scriptSetup?.content ?? '', template: descriptor.template?.content ?? '' };
}

describe('SystemSettingsPanel layout and interaction contract', () => {
  it('keeps tab drafts local and routes save, refresh, and reset to the active category', () => {
    const { script, template } = panelParts();

    expect(script).toContain("const activeTab = ref<SettingsTabKey>('system')");
    expect(script).toContain("if (activeTab.value === 'system') await saveSystemSettings()");
    expect(script).toContain("else if (activeTab.value === 'dashboard') await saveDashboardHeroSetting()");
    expect(script).toContain("if (activeTab.value === 'system') await loadSystemSettings()");
    expect(script).toContain("else if (activeTab.value === 'terminal') await loadTerminalSettingsSetting()");
    expect(script).toContain("if (activeTab.value === 'system') resetSystemSettingsDraft()");
    expect(template).toContain('@click="activeTab = tab.key"');
    expect(template).toContain(':disabled="!canSave || currentLoading || currentBusy"');
  });

  it('starts with preview collapsed, unmounts it when closed, and collapses it on tab changes', () => {
    const { script, template } = panelParts();

    expect(script).toContain('const previewExpanded = ref(false)');
    expect(script).toContain('watch(activeTab, () => { previewExpanded.value = false; })');
    expect(template).toContain(':aria-expanded="previewExpanded"');
    expect(template).toContain('aria-controls="system-settings-preview"');
    expect(template).toContain('v-if="previewExpanded" id="system-settings-preview"');
  });

  it('keeps navigation keyboard accessible and hides edit actions without permissions', () => {
    const { template } = panelParts();

    expect(template).toContain('v-if="canSave" type="primary"');
    expect(template).toContain(':aria-current="activeTab === tab.key ? \'page\' : undefined"');
    expect(template).toContain(':disabled="!canSave || currentLoading || currentBusy"');
    expect(template).toContain('class="system-settings-tabs"');
  });
});
