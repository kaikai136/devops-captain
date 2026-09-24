<template>
  <article class="onepanel-card" :class="{ 'onepanel-card--fill': fill }">
    <header v-if="title || $slots.header || $slots.actions" class="onepanel-card-header">
      <slot name="header">
        <h2 class="onepanel-card-title">{{ title }}</h2>
      </slot>
      <div v-if="$slots.actions" class="onepanel-card-actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="onepanel-card-body">
      <slot />
    </div>
  </article>
</template>

<script setup lang="ts">
defineOptions({ name: 'OnePanelCard' });

defineProps<{
  title?: string;
  fill?: boolean;
}>();
</script>
