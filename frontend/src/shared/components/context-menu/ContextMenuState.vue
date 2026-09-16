<script setup lang="ts">
import { watch } from 'vue';
import { injectContextMenuRootContext } from 'reka-ui';

const props = defineProps<{ open: boolean }>();
const context = injectContextMenuRootContext();

watch(() => props.open, (open) => {
  if (!open) context.onOpenChange(false);
});
</script>

<template></template>
