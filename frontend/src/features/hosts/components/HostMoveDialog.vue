<script setup lang="ts">
import { computed } from 'vue';

import type { ManagedHost } from '@features/hosts/types';
import type { HostMoveForm } from '@features/hosts/composables/useHostEditor';
import type { HostGroupRoot } from '@features/hosts/composables/useHostGroups';
import type { FlatHostGroup } from '@features/hosts/utils/groups';

const props = defineProps<{
  open: boolean;
  mode: 'single' | 'selected';
  form: HostMoveForm;
  hosts: ManagedHost[];
  root: HostGroupRoot;
  groups: FlatHostGroup[];
  selectedCount: number;
}>();

const emit = defineEmits<{
  close: [];
  submit: [];
  'update-form-field': [field: keyof HostMoveForm, value: number | null];
}>();

const hostId = computed({
  get: () => props.form.hostId,
  set: (value) => emit('update-form-field', 'hostId', value),
});
const targetGroup = computed({
  get: () => props.form.targetGroup,
  set: (value) => emit('update-form-field', 'targetGroup', value),
});
</script>

<template>
  <el-dialog :model-value="props.open" class="host-move-dialog" :title="props.mode === 'selected' ? '更新所选' : '移动主机'" :close-on-click-modal="false" @close="emit('close')">
    <form id="host-move-form" class="host-move-form" @submit.prevent="emit('submit')">
      <p v-if="props.mode === 'selected'" class="host-move-hint">仅支持更换主机分组，已选择 {{ props.selectedCount }} 台主机。</p>
      <label v-if="props.mode === 'single'">
        <span>选择主机</span>
        <el-select v-model="hostId">
          <el-option v-for="host in props.hosts" :key="host.id" :value="host.id" :label="`${host.name} · ${host.privateIp}`" />
        </el-select>
      </label>
      <label>
        <span>目标分组</span>
        <el-select v-model="targetGroup">
          <el-option disabled :value="null" :label="props.root.label" />
          <el-option v-for="group in props.groups" :key="group.key" :value="group.key" :label="`${'　'.repeat(group.level)}${group.label}`" />
        </el-select>
      </label>
    </form>
    <template #footer>
      <div class="popup-actions">
        <el-button @click="emit('close')">取消</el-button>
        <el-button class="primary" type="primary" @click="emit('submit')">{{ props.mode === 'selected' ? '更新' : '移动' }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>
