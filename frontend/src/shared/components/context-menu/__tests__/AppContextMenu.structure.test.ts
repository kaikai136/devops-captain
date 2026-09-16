import { parse } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

function source(name: string) {
  return readFileSync(new URL(`../${name}`, import.meta.url), 'utf8');
}

describe('shared shadcn-style context menu', () => {
  it('uses non-modal Reka primitives with portalled, viewport-aware contents', () => {
    const template = parse(source('AppContextMenu.vue')).descriptor.template?.content ?? '';
    expect(template).toContain('<ContextMenuRoot :modal="false"');
    expect(template).toContain('<ContextMenuTrigger as-child :disabled="disabled">');
    expect(template).toContain('<ContextMenuPortal>');
    expect(template).toContain(':collision-padding="8"');
    expect(template).toContain('@close-auto-focus.prevent');
    expect(template).not.toContain('@keydown.stop');
    expect(source('context-menu.css')).toContain('--reka-context-menu-content-available-height');
    expect(source('context-menu.css')).toContain('overflow-y: auto');
  });

  it('uses selection events and recursive submenus instead of hover-only buttons', () => {
    const template = parse(source('ContextMenuItems.vue')).descriptor.template?.content ?? '';
    expect(template).toContain('<ContextMenuSeparator');
    expect(template).toContain('<ContextMenuSubTrigger');
    expect(template).toContain('<ContextMenuSubContent');
    expect(template).toContain('<ContextMenuItems :items="item.children"');
    expect(template).toContain(':disabled="!item.enabled"');
    expect(template).toContain('@select="emit(\'select\', item)"');
    expect(template).not.toContain('@click="');
    expect(template).not.toContain('@keydown.stop');
    expect(source('ContextMenuEntryLabel.vue')).toContain('item.swatchColor');
    expect(source('ContextMenuEntryLabel.vue')).toContain('item.shortcut');
  });

  it('closes the primitive when the owning page resets its state', () => {
    expect(source('ContextMenuState.vue')).toContain('if (!open) context.onOpenChange(false)');
  });

  it('shares the menu with file entries and directory backgrounds', () => {
    const file = readFileSync(new URL('../../../../features/terminal/components/files/SftpPanel.vue', import.meta.url), 'utf8');
    expect(file).toContain(':open="fileContextMenu.visible || directoryContextMenu.visible"');
    expect(file).toContain(':items="fileContextMenu.visible ? fileContextMenuItems : directoryContextMenuItems"');
    expect(file).toContain('@select="runContextMenuItem"');
    expect(file).not.toContain('function submenuLeft');
  });
});
