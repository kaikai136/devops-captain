<script setup lang="ts">
import { computed } from 'vue';

import AppIcon from '@shared/components/AppIcon.vue';
import type { HostStatusFilter } from '@features/hosts/composables/useHostList';

export type HostColumnKey =
  | 'group'
  | 'name'
  | 'ip'
  | 'machine'
  | 'spec'
  | 'platformType'
  | 'user'
  | 'port'
  | 'createdAt'
  | 'updatedAt'
  | 'creator'
  | 'remark'
  | 'status'
  | 'actions';

export interface HostColumnOption {
  key: HostColumnKey;
  label: string;
  width: string;
  minWidth: number;
}

const props = defineProps<{
  search: string;
  statusFilter: HostStatusFilter;
  selectedCount: number;
  selectedVerifyingCount: number;
  moreActionsOpen: boolean;
  columnSettingsOpen: boolean;
  fullscreen: boolean;
  columns: readonly HostColumnOption[];
  columnVisibility: Record<HostColumnKey, boolean>;
  allColumnsVisible: boolean;
  someColumnsVisible: boolean;
  isOnlyVisibleColumn: (key: HostColumnKey) => boolean;
  canCreate: boolean;
  canManageQuickCommands: boolean;
  canUseMoreActions: boolean;
  canVerify: boolean;
  canFilter: boolean;
  canMove: boolean;
  canDelete: boolean;
  canBulkExecute: boolean;
  showMoreActionsDivider: boolean;
  canImport: boolean;
  canExport: boolean;
}>();

const emit = defineEmits<{
  'update:search': [value: string];
  create: [];
  'open-quick-commands': [];
  'toggle-more-actions': [];
  'status-filter': [filter: 'all' | 'unverified'];
  'verify-selected': [];
  'bulk-execute-selected': [];
  'upload-file-selected': [];
  'move-selected': [];
  'delete-selected': [];
  import: [];
  export: [];
  refresh: [];
  'toggle-column-settings': [];
  'toggle-all-columns': [value: Event | boolean | string | number];
  'reset-columns': [];
  'update-column': [key: HostColumnKey, value: Event | boolean | string | number];
  'toggle-fullscreen': [];
}>();

const searchModel = computed({
  get: () => props.search,
  set: (value: string) => emit('update:search', value),
});
</script>

<template>
  <div class="host-toolbar">
    <el-input v-model="searchModel" class="host-search-input" placeholder="输入别名/IP检索" clearable />
    <div class="host-toolbar-actions">
      <el-button v-if="props.canCreate" type="primary" @click="emit('create')"><AppIcon name="plus" :size="16" />新建</el-button>
      <el-button v-if="props.canManageQuickCommands" class="host-quick-command-trigger" @click="emit('open-quick-commands')">
        <AppIcon name="zap" :size="16" />
        快捷命令
      </el-button>
      <div v-if="props.canUseMoreActions" class="host-more-actions" @click.stop>
        <el-button
          class="more-action-trigger"
          :aria-expanded="props.moreActionsOpen"
          @click="emit('toggle-more-actions')"
        >
          更多操作
          <AppIcon name="chevronDown" :size="14" />
        </el-button>
        <div v-if="props.moreActionsOpen" class="host-more-menu">
          <el-button v-if="props.canVerify" text :disabled="!props.selectedCount || props.selectedVerifyingCount > 0" @click="emit('verify-selected')">
            <AppIcon name="shield" :size="15" />
            <span>{{ props.selectedVerifyingCount > 0 ? '验证中' : '验证所选' }}</span>
          </el-button>
          <el-button v-if="props.canBulkExecute" text :disabled="!props.selectedCount" @click="emit('bulk-execute-selected')">
            <AppIcon name="terminal" :size="15" />
            <span>批量执行</span>
          </el-button>
          <el-button v-if="props.canBulkExecute" text :disabled="!props.selectedCount" @click="emit('upload-file-selected')">
            <AppIcon name="upload" :size="15" />
            <span>上传文件</span>
          </el-button>
          <el-button v-if="props.canFilter" text :class="{ active: props.statusFilter === 'all' }" @click="emit('status-filter', 'all')">
            <AppIcon name="search" :size="15" />
            <span>查询全部</span>
          </el-button>
          <el-button v-if="props.canFilter" text :class="{ active: props.statusFilter === 'unverified' }" @click="emit('status-filter', 'unverified')">
            <AppIcon name="circleHelp" :size="15" />
            <span>查未验证</span>
          </el-button>
          <hr v-if="props.showMoreActionsDivider" />
          <el-button v-if="props.canMove" text :disabled="!props.selectedCount" @click="emit('move-selected')">
            <AppIcon name="upload" :size="15" />
            <span>更新所选</span>
          </el-button>
          <el-button v-if="props.canDelete" class="danger" text :disabled="!props.selectedCount" @click="emit('delete-selected')">
            <AppIcon name="trash" :size="15" />
            <span>删除所选</span>
          </el-button>
        </div>
      </div>
      <el-tooltip v-if="props.canImport" content="导入" placement="bottom">
        <el-button class="icon-only" circle aria-label="导入" @click="emit('import')"><AppIcon name="download" :size="16" /></el-button>
      </el-tooltip>
      <el-tooltip v-if="props.canExport" content="导出" placement="bottom">
        <el-button class="icon-only" circle aria-label="导出" @click="emit('export')"><AppIcon name="upload" :size="16" /></el-button>
      </el-tooltip>
      <el-tooltip content="刷新" placement="bottom">
        <el-button class="icon-only" circle aria-label="刷新" @click="emit('refresh')"><AppIcon name="refresh" :size="16" /></el-button>
      </el-tooltip>
      <div class="host-column-settings" @click.stop>
        <el-tooltip content="列设置" placement="bottom">
          <el-button
          class="icon-only"
          circle
          aria-label="列设置"
          :aria-expanded="props.columnSettingsOpen"
          @click="emit('toggle-column-settings')"
        >
          <AppIcon name="settings" :size="16" />
          </el-button>
        </el-tooltip>
        <div v-if="props.columnSettingsOpen" class="host-column-menu">
          <div class="host-column-menu-head">
            <el-checkbox
              class="host-column-all"
              :model-value="props.allColumnsVisible"
              :indeterminate="props.someColumnsVisible && !props.allColumnsVisible"
                @change="emit('toggle-all-columns', $event)"
            >
              列显示
            </el-checkbox>
            <el-button link type="primary" class="host-column-reset" @click="emit('reset-columns')">重置</el-button>
          </div>
          <div class="host-column-options">
            <el-checkbox
              v-for="column in props.columns"
              :key="column.key"
              class="host-column-option"
              :model-value="props.columnVisibility[column.key]"
                :disabled="props.isOnlyVisibleColumn(column.key)"
                @change="emit('update-column', column.key, $event)"
            >
              {{ column.label }}
            </el-checkbox>
          </div>
        </div>
      </div>
      <el-tooltip :content="props.fullscreen ? '退出全屏' : '全屏'" placement="bottom">
        <el-button class="icon-only" circle :aria-label="props.fullscreen ? '退出全屏' : '全屏'" @click.stop="emit('toggle-fullscreen')">
          <AppIcon :name="props.fullscreen ? 'minimize' : 'maximize'" :size="18" />
        </el-button>
      </el-tooltip>
    </div>
  </div>
</template>
