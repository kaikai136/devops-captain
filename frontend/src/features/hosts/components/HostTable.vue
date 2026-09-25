<script setup lang="ts">
import AppIcon from '@shared/components/AppIcon.vue';
import AppPagination from '@shared/components/AppPagination.vue';
import type { ManagedHost } from '@features/hosts/types';
import type { HostSortKey, SortDirection } from '@features/hosts/utils/groups';
import type { HostColumnKey } from './HostToolbar.vue';

const props = defineProps<{
  hosts: ManagedHost[];
  visibleHostCount: number;
  selectedIds: Set<number>;
  visibleIds: number[];
  allVisibleSelected: boolean;
  someVisibleSelected: boolean;
  tableStyle: Record<string, string>;
  sortKey: HostSortKey;
  sortDirection: SortDirection;
  page: number;
  pageSize: number;
  selectedCount: number;
  selectedVerifyingCount: number;
  stats: { total: number; verified: number; unverified: number };
  loading: boolean;
  verifyingIds: Set<number>;
  canOpenTerminal: boolean;
  canEdit: boolean;
  canVerify: boolean;
  canMove: boolean;
  canDelete: boolean;
  canBulkExecute: boolean;
  canUseRowActions: boolean;
  isColumnVisible: (key: HostColumnKey) => boolean;
  groupName: (groupId: number) => string;
  sortMark: (key: HostSortKey) => string;
  formatDate: (value: string | null | undefined) => string;
  platformType: (value: string | null | undefined) => string;
}>();

const emit = defineEmits<{
  'toggle-all-visible': [value: Event | boolean | string | number];
  'toggle-host': [hostId: number, value: Event | boolean | string | number];
  sort: [key: HostSortKey];
  'resize-column-start': [key: HostColumnKey, event: MouseEvent];
  'open-terminal': [host: ManagedHost];
  'open-simple-terminal': [host: ManagedHost];
  edit: [host: ManagedHost];
  verify: [host: ManagedHost];
  delete: [host: ManagedHost];
  'page-change': [page: number];
  'page-size-change': [pageSize: number];
  'clear-selection': [];
  'verify-selected': [];
  'bulk-execute-selected': [];
  'move-selected': [];
  'delete-selected': [];
}>();

function formatHostSpec(host: ManagedHost) {
  if (!host.verified || host.cpu <= 0 || host.memory <= 0) return '-';
  const disk = typeof host.disk === 'string' && host.disk.trim() ? host.disk.trim() : '-';
  return `${host.cpu}C / ${host.memory}G / ${disk}`;
}

function formatHostSystem(host: ManagedHost) {
  return [host.systemType, host.systemArch].filter(Boolean).join(' - ') || '-';
}
</script>

<template>
  <div class="host-table-scroll">
    <div class="host-table app-data-grid" :style="props.tableStyle">
      <div class="host-table-row head">
        <label class="host-select-cell" aria-label="选择所有可见主机">
          <el-checkbox
            :model-value="props.allVisibleSelected"
            :disabled="!props.visibleIds.length"
            :indeterminate="props.someVisibleSelected && !props.allVisibleSelected"
            @change="emit('toggle-all-visible', $event)"
          />
        </label>
        <div v-if="props.isColumnVisible('group')" class="host-table-head-cell">
          <span>主机分组</span>
          <span class="host-column-resize-handle" role="separator" aria-label="调整主机分组列宽" @mousedown="emit('resize-column-start', 'group', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('name')" class="host-table-head-cell">
          <el-button text class="host-sort-button" :class="{ active: props.sortKey === 'name', desc: props.sortKey === 'name' && props.sortDirection === 'desc' }" @click="emit('sort', 'name')">
            节点 <em>{{ props.sortMark('name') }}</em>
          </el-button>
          <span class="host-column-resize-handle" role="separator" aria-label="调整节点列宽" @mousedown="emit('resize-column-start', 'name', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('ip')" class="host-table-head-cell">
          <el-button text class="host-sort-button" :class="{ active: props.sortKey === 'ip', desc: props.sortKey === 'ip' && props.sortDirection === 'desc' }" @click="emit('sort', 'ip')">
            IP地址 <em>{{ props.sortMark('ip') }}</em>
          </el-button>
          <span class="host-column-resize-handle" role="separator" aria-label="调整IP地址列宽" @mousedown="emit('resize-column-start', 'ip', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('machine')" class="host-table-head-cell">
          <span>机器名称</span>
          <span class="host-column-resize-handle" role="separator" aria-label="调整机器名称列宽" @mousedown="emit('resize-column-start', 'machine', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('spec')" class="host-table-head-cell">
          <span>主机规格</span>
          <span class="host-column-resize-handle" role="separator" aria-label="调整主机规格列宽" @mousedown="emit('resize-column-start', 'spec', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('platformType')" class="host-table-head-cell">
          <el-button text class="host-sort-button" :class="{ active: props.sortKey === 'platformType', desc: props.sortKey === 'platformType' && props.sortDirection === 'desc' }" @click="emit('sort', 'platformType')">
            平台类型 <em>{{ props.sortMark('platformType') }}</em>
          </el-button>
          <span class="host-column-resize-handle" role="separator" aria-label="调整平台类型列宽" @mousedown="emit('resize-column-start', 'platformType', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('user')" class="host-table-head-cell">
          <span>用户</span>
          <span class="host-column-resize-handle" role="separator" aria-label="调整用户列宽" @mousedown="emit('resize-column-start', 'user', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('port')" class="host-table-head-cell">
          <span>端口</span>
          <span class="host-column-resize-handle" role="separator" aria-label="调整端口列宽" @mousedown="emit('resize-column-start', 'port', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('createdAt')" class="host-table-head-cell">
          <el-button text class="host-sort-button" :class="{ active: props.sortKey === 'createdAt', desc: props.sortKey === 'createdAt' && props.sortDirection === 'desc' }" @click="emit('sort', 'createdAt')">
            创建时间 <em>{{ props.sortMark('createdAt') }}</em>
          </el-button>
          <span class="host-column-resize-handle" role="separator" aria-label="调整创建时间列宽" @mousedown="emit('resize-column-start', 'createdAt', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('updatedAt')" class="host-table-head-cell">
          <el-button text class="host-sort-button" :class="{ active: props.sortKey === 'updatedAt', desc: props.sortKey === 'updatedAt' && props.sortDirection === 'desc' }" @click="emit('sort', 'updatedAt')">
            更新时间 <em>{{ props.sortMark('updatedAt') }}</em>
          </el-button>
          <span class="host-column-resize-handle" role="separator" aria-label="调整更新时间列宽" @mousedown="emit('resize-column-start', 'updatedAt', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('creator')" class="host-table-head-cell">
          <el-button text class="host-sort-button" :class="{ active: props.sortKey === 'creator', desc: props.sortKey === 'creator' && props.sortDirection === 'desc' }" @click="emit('sort', 'creator')">
            创建者 <em>{{ props.sortMark('creator') }}</em>
          </el-button>
          <span class="host-column-resize-handle" role="separator" aria-label="调整创建者列宽" @mousedown="emit('resize-column-start', 'creator', $event)"></span>
        </div>
        <div v-if="props.isColumnVisible('remark')" class="host-table-head-cell">
          <span>备注</span>
          <span class="host-column-resize-handle" role="separator" aria-label="调整备注列宽" @mousedown="emit('resize-column-start', 'remark', $event)"></span>
        </div>
        <span v-if="props.isColumnVisible('status')" class="host-sticky-cell host-status-cell">状态</span>
        <span v-if="props.isColumnVisible('actions')" class="host-sticky-cell host-actions-cell">操作</span>
      </div>
      <div v-for="host in props.hosts" :key="host.id" class="host-table-row">
        <label class="host-select-cell" :aria-label="`选择主机 ${host.name}`">
          <el-checkbox
            :model-value="props.selectedIds.has(host.id)"
            @change="emit('toggle-host', host.id, $event)"
          />
        </label>
        <span v-if="props.isColumnVisible('group')" class="host-group-cell">{{ props.groupName(host.group) }}</span>
        <el-button v-if="props.isColumnVisible('name') && props.canOpenTerminal" text class="host-name-link" @click="emit('open-terminal', host)">{{ host.name }}</el-button>
        <span v-else-if="props.isColumnVisible('name')" class="host-name-text">{{ host.name }}</span>
        <div v-if="props.isColumnVisible('ip')" class="host-ip-stack">
          <span v-if="host.publicIp"><i class="ip-tag public">公</i>{{ host.publicIp }}</span>
          <span>{{ host.privateIp }}</span>
        </div>
        <span v-if="props.isColumnVisible('machine')" class="host-machine-cell" :title="host.machineName">{{ host.verified ? host.machineName : '' }}</span>
        <div v-if="props.isColumnVisible('spec')" class="host-spec-cell">
          <span>
            <strong>规格:</strong>
            <em :title="formatHostSpec(host)">{{ formatHostSpec(host) }}</em>
          </span>
          <span>
            <strong>系统:</strong>
            <em :title="formatHostSystem(host)">{{ formatHostSystem(host) }}</em>
          </span>
        </div>
        <div v-if="props.isColumnVisible('platformType')" class="host-platform-cell">
          <span class="host-platform-type" :class="props.platformType(host.platformType)">
            {{ props.platformType(host.platformType) }}
          </span>
        </div>
        <span v-if="props.isColumnVisible('user')" class="host-user-cell">{{ host.loginUser || '-' }}</span>
        <span v-if="props.isColumnVisible('port')" class="host-port-cell">{{ host.port || 22 }}</span>
        <span v-if="props.isColumnVisible('createdAt')" class="host-date-cell">{{ props.formatDate(host.createdAt) }}</span>
        <span v-if="props.isColumnVisible('updatedAt')" class="host-date-cell">{{ props.formatDate(host.updatedAt) }}</span>
        <span v-if="props.isColumnVisible('creator')" class="host-creator-cell">{{ host.creator || '-' }}</span>
        <span v-if="props.isColumnVisible('remark')" class="host-remark-cell" :title="host.remark">{{ host.remark || '-' }}</span>
        <div v-if="props.isColumnVisible('status')" class="host-sticky-cell host-status-cell">
          <span class="verify-badge" :class="{ verified: host.verified, failed: host.verifyStatus === 'failed' }">
            {{ host.verified ? '已验证' : host.verifyStatus === 'failed' ? '验证失败' : '未验证' }}
          </span>
        </div>
        <div v-if="props.isColumnVisible('actions')" class="host-actions host-sticky-cell host-actions-cell">
          <el-button v-if="props.canEdit" text class="host-action-icon" title="编辑" aria-label="编辑" @click="emit('edit', host)">
            <AppIcon name="edit" :size="16" />
          </el-button>
          <el-button
            v-if="props.canVerify"
            text
            class="host-action-icon"
            :class="{ 'is-verifying': props.verifyingIds.has(host.id) }"
            :disabled="props.verifyingIds.has(host.id)"
            :title="props.verifyingIds.has(host.id) ? '验证中' : '验证'"
            :aria-label="props.verifyingIds.has(host.id) ? '验证中' : '验证'"
            @click="emit('verify', host)"
          >
            <AppIcon name="rotate" :size="16" />
          </el-button>
          <el-button v-if="props.canOpenTerminal" text class="host-action-icon" title="终端" aria-label="终端" @click="emit('open-simple-terminal', host)">
            <AppIcon name="terminal" :size="16" />
          </el-button>
          <el-button v-if="props.canDelete" text class="host-action-icon danger" title="删除" aria-label="删除" @click="emit('delete', host)">
            <AppIcon name="trash" :size="16" />
          </el-button>
          <span v-if="!props.canUseRowActions" class="host-action-placeholder">-</span>
        </div>
      </div>
      <el-empty v-if="!props.visibleHostCount" class="host-empty" description="没有匹配的主机" />
    </div>
  </div>
  <div class="host-pagination" aria-label="主机列表分页">
    <div class="host-pagination-controls">
      <AppPagination
        :page="props.page"
        :page-size="props.pageSize"
        :total="props.visibleHostCount"
        @page-change="emit('page-change', $event)"
        @page-size-change="emit('page-size-change', $event)"
      />
    </div>
    <div class="host-stats-line">
      <span>共 {{ props.stats.total }} 台主机</span>
      <span>已验证 {{ props.stats.verified }}</span>
      <span>未验证 {{ props.stats.unverified }}</span>
      <span v-if="props.loading">加载中</span>
    </div>
  </div>

  <div v-if="props.selectedCount" class="host-bulk-action-bar" @click.stop>
    <div class="host-bulk-action-info">
      <span class="host-bulk-action-icon"><AppIcon name="info" :size="16" /></span>
      <div class="host-bulk-action-copy">
        <strong>批量操作</strong>
        <span class="host-bulk-action-count">已选择 {{ props.selectedCount }} 个主机</span>
      </div>
    </div>
    <div class="host-bulk-action-buttons">
      <el-button class="host-bulk-button host-bulk-button-cancel" @click="emit('clear-selection')">取消选中</el-button>
      <el-button
        v-if="props.canVerify"
        class="host-bulk-button host-bulk-button-verify"
        :disabled="props.selectedVerifyingCount > 0"
        @click="emit('verify-selected')"
      >
        {{ props.selectedVerifyingCount > 0 ? '验证中' : '验证所选' }}
      </el-button>
      <el-button v-if="props.canBulkExecute" class="host-bulk-button host-bulk-button-execute" @click="emit('bulk-execute-selected')">
        <AppIcon name="terminal" :size="14" />
        批量执行
      </el-button>
      <el-button v-if="props.canMove" class="host-bulk-button host-bulk-button-update" @click="emit('move-selected')">更新所选</el-button>
      <el-button v-if="props.canDelete" class="host-bulk-button host-bulk-button-delete" @click="emit('delete-selected')">删除所选</el-button>
    </div>
  </div>
</template>
