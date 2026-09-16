<script setup lang="ts">
import {
  ContextMenuItem,
  ContextMenuPortal,
  ContextMenuSeparator,
  ContextMenuSub,
  ContextMenuSubContent,
  ContextMenuSubTrigger,
} from 'reka-ui';
import ContextMenuEntryLabel from './ContextMenuEntryLabel.vue';
import type { ContextMenuEntry } from './types';

defineProps<{ items: ContextMenuEntry[] }>();
const emit = defineEmits<{ select: [item: ContextMenuEntry] }>();
</script>

<template>
  <template v-for="item in items" :key="item.id">
    <ContextMenuSeparator v-if="item.separatorBefore" class="shadcn-context-menu-separator" />
    <ContextMenuSub v-if="item.children?.length">
      <ContextMenuSubTrigger class="shadcn-context-menu-item" :disabled="!item.enabled" :text-value="item.label">
        <ContextMenuEntryLabel :item="item" />
      </ContextMenuSubTrigger>
      <ContextMenuPortal>
        <ContextMenuSubContent
          class="shadcn-context-menu-content"
          :side-offset="4"
          :align-offset="-4"
          :collision-padding="8"
          loop
          @click.stop
          @contextmenu.prevent.stop
        >
          <ContextMenuItems :items="item.children" @select="emit('select', $event)" />
        </ContextMenuSubContent>
      </ContextMenuPortal>
    </ContextMenuSub>
    <ContextMenuItem
      v-else
      class="shadcn-context-menu-item"
      :data-variant="item.danger ? 'destructive' : undefined"
      :disabled="!item.enabled"
      :text-value="item.label"
      @select="emit('select', item)"
    >
      <ContextMenuEntryLabel :item="item" />
    </ContextMenuItem>
  </template>
</template>
