import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const table = readFileSync(new URL('../FileTable.vue', import.meta.url), 'utf8');
const panel = readFileSync(new URL('../SftpPanel.vue', import.meta.url), 'utf8');

describe('file browser path navigation', () => {
  it('allows typing a draft and submitting with Enter or the directory button', () => {
    expect(table).toContain('v-model="pathDraft"');
    expect(table).toContain('@keydown.enter.stop.prevent="navigateToPath"');
    expect(table).toContain('@click="navigateToPath()"');
    expect(table).toContain("if (target) emit('navigate', target)");
    expect(panel).toContain('@navigate="browser.loadDirectory($event)"');
  });

  it('syncs successful navigation, supports Escape, and guards unavailable sessions and composition', () => {
    expect(table).toContain('pathDraft.value = props.path');
    expect(table).toContain('@keydown.esc.stop.prevent="pathDraft = path"');
    expect(table).toContain('event?.isComposing || !props.active || props.loading');
    expect(table).toContain(':readonly="loading"');
  });
});
