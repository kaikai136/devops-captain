<script setup lang="ts">
import { computed } from 'vue';

import type {
  HostExportColumnKey,
  HostExportColumnOption,
  HostExportScope,
  HostTransferFormat,
} from '@features/hosts/types';

const props = defineProps<{
  scope: HostExportScope;
  format: HostTransferFormat;
  columns: readonly HostExportColumnOption[];
  selectedColumns: Set<HostExportColumnKey>;
  allColumnsSelected: boolean;
  selectedCount: number;
}>();

const emit = defineEmits<{
  close: [];
  confirm: [];
  'update:scope': [scope: HostExportScope];
  'update:format': [format: HostTransferFormat];
  'toggle-column': [column: HostExportColumnKey, value: boolean | string | number];
  'toggle-all-columns': [value: boolean | string | number];
}>();

const selectedScope = computed({
  get: () => props.scope,
  set: (value) => emit('update:scope', value),
});
const selectedFormat = computed({
  get: () => props.format,
  set: (value) => emit('update:format', value),
});
</script>

<template>
  <el-dialog class="host-transfer-modal host-export-modal" :model-value="true" title="导出实例数据" width="748px" align-center :close-on-click-modal="false" @close="emit('close')">
        <div class="host-export-body popup-body">
          <section class="export-section">
          <span class="export-section-title">需要导出的实例</span>
          <el-radio-group v-model="selectedScope" class="export-scope-grid">
            <el-radio value="all" class="export-scope-card" :class="{ active: selectedScope === 'all' }">
              <span class="export-scope-copy">
                <strong>所有实例</strong>
                <em>导出当前主机列表下的所有实例</em>
              </span>
            </el-radio>
            <el-radio value="selected" class="export-scope-card" :class="{ active: selectedScope === 'selected' }">
              <span class="export-scope-copy">
                <strong>已选中的实例 {{ props.selectedCount }}</strong>
                <em>导出当前列表中所选中的实例</em>
              </span>
            </el-radio>
          </el-radio-group>
          </section>

          <section class="export-section">
          <span class="export-section-title">需要导出的数据列</span>
          <el-checkbox class="export-check-all" :model-value="props.allColumnsSelected" :indeterminate="props.selectedColumns.size > 0 && !props.allColumnsSelected" @change="emit('toggle-all-columns', $event)">全选</el-checkbox>
          <div class="export-column-grid">
            <el-checkbox v-for="column in props.columns" :key="column.field" class="export-column-option" :model-value="props.selectedColumns.has(column.field)" @change="emit('toggle-column', column.field, $event)">
              <span>{{ column.label }}</span>
            </el-checkbox>
          </div>
          </section>

          <section class="export-section">
          <span class="export-section-title">导出文件格式</span>
          <el-radio-group v-model="selectedFormat" class="export-format-row">
            <el-radio value="excel">Excel</el-radio>
            <el-radio value="json">JSON</el-radio>
          </el-radio-group>
          </section>
        </div>
      <template #footer>
        <div class="popup-footer popup-actions">
          <el-button @click="emit('close')">取消</el-button>
          <el-button type="primary" @click="emit('confirm')">确定</el-button>
        </div>
      </template>
  </el-dialog>
</template>
