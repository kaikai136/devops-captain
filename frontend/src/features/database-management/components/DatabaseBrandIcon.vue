<script setup lang="ts">
import { computed } from 'vue';
import { Database } from '@lucide/vue';
import { databaseBrandLogo } from '../utils/databaseBrand';

const props = defineProps<{ dbType: string; connected: boolean }>();
const logo = computed(() => databaseBrandLogo(props.dbType));
</script>

<template>
  <span class="db-brand-icon" :class="{ 'is-connected': connected }" aria-hidden="true">
    <img v-if="logo" :src="logo" alt="" width="18" height="18" draggable="false" />
    <Database v-else :size="18" />
  </span>
</template>

<style scoped>
.db-brand-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 18px;
  height: 18px;
  color: var(--el-text-color-secondary, #909399);
  filter: grayscale(1);
  opacity: 0.5;
}
.db-brand-icon.is-connected {
  filter: none;
  opacity: 1;
}
.db-brand-icon img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
</style>
