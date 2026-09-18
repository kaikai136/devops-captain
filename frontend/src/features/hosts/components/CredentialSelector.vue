<script setup lang="ts">
import { computed } from 'vue';

import type { HostCredential } from '@features/hosts/types';

const props = defineProps<{
  credentials: HostCredential[];
  modelValue: number | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: number | null];
  change: [value: number | null];
}>();

const selectedCredential = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
});
</script>

<template>
  <el-select v-model="selectedCredential" :teleported="false" @change="emit('change', selectedCredential)">
    <el-option :value="null" label="手动输入" />
    <el-option v-for="credential in props.credentials" :key="credential.id" :value="credential.id" :label="`${credential.name}（${credential.username}）`" />
  </el-select>
</template>
