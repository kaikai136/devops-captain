<script setup lang="ts">
import { ContextMenuContent, ContextMenuPortal, ContextMenuRoot, ContextMenuTrigger } from 'reka-ui';
import ContextMenuItems from './ContextMenuItems.vue';
import ContextMenuState from './ContextMenuState.vue';
import type { ContextMenuEntry } from './types';
import './context-menu.css';

withDefaults(defineProps<{
  open: boolean;
  items: ContextMenuEntry[];
  label?: string;
  disabled?: boolean;
}>(), { label: '\u64cd\u4f5c\u83dc\u5355', disabled: false });
const emit = defineEmits<{
  'update:open': [open: boolean];
  select: [item: ContextMenuEntry];
}>();
</script>

<template>
  <ContextMenuRoot :modal="false" @update:open="emit('update:open', $event)">
    <ContextMenuState :open="open" />
    <ContextMenuTrigger as-child :disabled="disabled">
      <slot />
    </ContextMenuTrigger>
    <ContextMenuPortal>
      <ContextMenuContent
        class="shadcn-context-menu-content"
        :aria-label="label"
        :collision-padding="8"
        loop
        @click.stop
        @contextmenu.prevent.stop
        @close-auto-focus.prevent
      >
        <ContextMenuItems :items="items" @select="emit('select', $event)" />
      </ContextMenuContent>
    </ContextMenuPortal>
  </ContextMenuRoot>
</template>
