import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function panelSource() {
  return readFileSync(fileURLToPath(new URL('../SystemSettingsPanel.vue', import.meta.url)), 'utf8');
}

describe('SystemSettingsPanel terminal settings structure', () => {
  it('adds a terminal tab backed by the terminal_settings system key', () => {
    const descriptor = parseSfc(panelSource(), { filename: 'SystemSettingsPanel.vue' }).descriptor;
    const script = descriptor.scriptSetup?.content ?? '';
    const template = descriptor.template?.content ?? '';

    expect(script).toContain("'terminal'");
    expect(script).toContain("const TERMINAL_SETTINGS_SETTING_KEY = 'terminal_settings'");
    expect(script).toContain('terminalSettingsDraft');
    expect(template).toContain("activeTab === 'terminal'");
    expect(script).toContain("title: '终端设置'");
    expect(template).toContain('sshConnectTimeoutSeconds');
    expect(template).toContain('sshBannerTimeoutSeconds');
    expect(template).toContain('sshAuthTimeoutSeconds');
    expect(template).toContain('sshConnectAttempts');
    expect(template).toContain('sshRetryDelayMs');
    expect(template).toContain('sshKeepaliveSeconds');
    expect(template).toContain('webSocketHeartbeatSeconds');
    expect(template).toContain('idleDisconnectMinutes');
    expect(template).toContain('initialReadTimeoutSeconds');
    expect(template).toContain('initialReadIdleTimeoutMs');
    expect(template).toContain('commandReadTimeoutSeconds');
    expect(template).toContain('commandReadIdleTimeoutMs');
    expect(template).toContain('readerPollIntervalMs');
    expect(template).toContain('cwdHookSuppressEchoMs');
    expect(template).toContain('cwdHookDrainTimeoutMs');
    expect(template).toContain('cwdHookDrainIdleTimeoutMs');
    expect(template).toContain('defaultCols');
    expect(template).toContain('defaultRows');
    expect(template).toContain('defaultFontSize');
    expect(template).toContain('scrollbackLines');
    expect(template).toContain('bulkExecutionMaxTargets');
    expect(template).toContain(':max="1000"');
  });
});
