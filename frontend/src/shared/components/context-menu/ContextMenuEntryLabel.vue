<script setup lang="ts">
import AppIcon from '../AppIcon.vue';
import type { ContextMenuEntry } from './types';

defineProps<{ item: ContextMenuEntry }>();
</script>

<template>
  <span v-if="item.swatchColor" class="shadcn-context-menu-swatch" :style="{ background: item.swatchColor }">
    <AppIcon v-if="item.selected" name="check" :size="12" />
  </span>
  <AppIcon v-else :name="item.selected ? 'check' : item.icon" :size="16" />
  <span class="shadcn-context-menu-label">{{ item.label }}</span>
  <span v-if="item.shortcut" class="shadcn-context-menu-shortcut">{{ item.shortcut }}</span>
  <AppIcon v-if="item.children?.length" name="chevronRight" :size="16" />
</template>
