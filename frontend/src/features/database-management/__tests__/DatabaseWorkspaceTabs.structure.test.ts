import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function readTabs() {
  return readFileSync(fileURLToPath(new URL('../components/DatabaseWorkspaceTabs.vue', import.meta.url)), 'utf8');
}

describe('database workspace tabs', () => {
  it('keeps the list tab fixed and supports asset tab closing', () => {
    const source = readTabs();

    expect(source).toContain("kind: 'list' | 'asset'");
    expect(source).toContain('item.sticky');
    expect(source).toContain('db-workspace-tab-close');
    expect(source).toContain("emit('close', item.id)");
    expect(source).toContain('aria-selected');
  });

  it('supports drag ordering and HexHub-style context actions', () => {
    const source = readTabs();

    expect(source).toContain('@dragstart="startDrag($event, item.id)"');
    expect(source).toContain('@drop="dropTab($event, item.id)"');
    expect(source).toContain("'close-others'");
    expect(source).toContain("'close-all'");
    expect(source).toContain("'copy'");
    expect(source).toContain('db-workspace-tab-menu');
  });
});
