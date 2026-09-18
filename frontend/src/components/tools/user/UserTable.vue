<script setup lang="ts">
import { formatDateTime } from '../../../utils/datetime';
import type { SystemUser, UserColumnKey } from '../../../composables/features/useUserManager';

const props = defineProps<{
  users: SystemUser[];
  filteredCount: number;
  isLoading: boolean;
  page: number;
  pageSize: number;
  totalPages: number;
  tableStyle: Record<string, string>;
  isColumnVisible: (key: UserColumnKey) => boolean;
  roleNames: (user: SystemUser) => string;
  loginStateText: (user: SystemUser) => string;
  twoFactorStatusClass: (user: SystemUser) => string;
  sessionAuditEnabled: (user: SystemUser) => boolean;
  canUsePageAction: (pageKey: string, actionKey: string) => boolean;
}>();

const emit = defineEmits<{
  toggleStatus: [user: SystemUser];
  enableTwoFactor: [user: SystemUser];
  disableTwoFactor: [user: SystemUser];
  resetTwoFactor: [user: SystemUser];
  toggleSessionAudit: [user: SystemUser];
  edit: [user: SystemUser];
  resetPassword: [user: SystemUser];
  delete: [user: SystemUser];
  updatePage: [page: number];
  updatePageSize: [pageSize: number];
}>();

function toggleTwoFactor(user: SystemUser) {
  if (user.twoFactorStatus === 'disabled' || !user.twoFactorStatus) {
    emit('enableTwoFactor', user);
    return;
  }
  emit('disableTwoFactor', user);
}

function twoFactorSwitchText(user: SystemUser) {
  return user.twoFactorStatus === 'enabled' ? '开启' : '关闭';
}

function canToggleTwoFactor(user: SystemUser) {
  return user.twoFactorStatus === 'enabled' ? props.canUsePageAction('users', '2fa_disable') : props.canUsePageAction('users', '2fa_enable');
}

function hasTwoFactorActions(user: SystemUser) {
  if (user.twoFactorStatus === 'required') return false;
  return canToggleTwoFactor(user) || props.canUsePageAction('users', '2fa_reset');
}

function sessionAuditSwitchText(user: SystemUser) {
  return props.sessionAuditEnabled(user) ? '开' : '关';
}

function hasRowActions() {
  return (
    props.canUsePageAction('users', 'toggle_status') ||
    props.canUsePageAction('users', 'edit') ||
    props.canUsePageAction('users', 'reset_password') ||
    props.canUsePageAction('users', 'delete')
  );
}
</script>

<template>
  <div class="user-table" :style="tableStyle">
    <div class="user-table-scroll">
      <el-table :data="users" row-key="id" :empty-text="isLoading ? '加载中...' : '暂无匹配账户'">
      <el-table-column v-if="isColumnVisible('username')" label="登录名" min-width="150">
        <template #default="{ row }">
          <div class="user-login-name">
            <strong>{{ row.username }}</strong>
            <el-tag v-if="row.isBuiltinAdmin" type="info" size="small" effect="dark">内置</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('name')" label="姓名" min-width="120">
        <template #default="{ row }">{{ row.firstName || '-' }}</template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('roles')" label="角色" min-width="140">
        <template #default="{ row }">{{ roleNames(row) || '-' }}</template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('status')" label="状态" min-width="120">
        <template #default="{ row }">
          <el-tag :type="row.isActive ? 'success' : 'danger'" size="small" effect="dark">
            {{ loginStateText(row) === '可登录' ? '正常' : loginStateText(row) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('lastLogin')" label="最近登录" min-width="180">
        <template #default="{ row }">{{ formatDateTime(row.lastLogin) }}</template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('sessionAudit')" label="会话审计" min-width="140">
        <template #default="{ row }">
          <el-switch
            v-if="canUsePageAction('users', 'session_audit')"
            :model-value="sessionAuditEnabled(row)"
            inline-prompt
            active-text="开"
            inactive-text="关"
            :disabled="row.isBuiltinAdmin"
            @change="$emit('toggleSessionAudit', row)"
          />
          <span v-else class="permission-placeholder">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('twoFactor')" label="2FA" min-width="180">
        <template #default="{ row }">
          <span v-if="row.twoFactorStatus === 'required'" class="user-2fa-pending">待验证</span>
          <template v-else-if="hasTwoFactorActions(row)">
            <el-switch
              v-if="canToggleTwoFactor(row)"
              :model-value="row.twoFactorStatus === 'enabled'"
              inline-prompt
              :active-text="twoFactorSwitchText(row)"
              :inactive-text="twoFactorSwitchText(row)"
              :disabled="row.isBuiltinAdmin"
              @change="toggleTwoFactor(row)"
            />
            <el-button
              v-if="canUsePageAction('users', '2fa_reset')"
              size="small"
              text
              type="primary"
              :disabled="row.isBuiltinAdmin"
              @click="$emit('resetTwoFactor', row)"
            >
              重置
            </el-button>
          </template>
          <span v-else class="permission-placeholder">-</span>
        </template>
      </el-table-column>
      <el-table-column v-if="isColumnVisible('actions')" label="操作" min-width="240" fixed="right">
        <template #default="{ row }">
          <div class="user-row-actions">
            <el-button v-if="canUsePageAction('users', 'toggle_status')" size="small" :disabled="row.isBuiltinAdmin" @click="$emit('toggleStatus', row)">
              {{ row.isActive ? '禁用' : '启用' }}
            </el-button>
            <el-button v-if="canUsePageAction('users', 'edit')" size="small" type="primary" :disabled="row.isBuiltinAdmin" @click="$emit('edit', row)">
              编辑
            </el-button>
            <el-button v-if="canUsePageAction('users', 'reset_password')" size="small" @click="$emit('resetPassword', row)">
              重置密码
            </el-button>
            <el-button v-if="canUsePageAction('users', 'delete')" size="small" type="danger" :disabled="row.isBuiltinAdmin" @click="$emit('delete', row)">
              删除
            </el-button>
            <span v-if="!hasRowActions()" class="permission-placeholder">-</span>
          </div>
        </template>
      </el-table-column>
      </el-table>
    </div>

    <div v-show="filteredCount > 0" class="user-table-pagination" aria-label="用户列表分页">
      <el-pagination
        class="user-koi-pagination"
        background
        layout="total, sizes, prev, pager, next, jumper"
        :current-page="page"
        :page-size="pageSize"
        :page-sizes="[10, 20, 50, 100, 200]"
        :total="filteredCount"
        @current-change="$emit('updatePage', $event)"
        @size-change="$emit('updatePageSize', $event)"
      />
    </div>
  </div>
</template>
