<script setup lang="ts">
import { ref } from 'vue';

import { useAppContext } from '@app/context';
import { useUserManager, userColumnOptions } from '../../composables/features/useUserManager';
import AppIcon from '@shared/components/AppIcon.vue';
import SystemSearchPanel from '@shared/components/SystemSearchPanel.vue';
import UserAccountDialog from './user/UserAccountDialog.vue';
import UserDeleteDialog from './user/UserDeleteDialog.vue';
import UserResetPasswordDialog from './user/UserResetPasswordDialog.vue';
import UserResetTwoFactorDialog from './user/UserResetTwoFactorDialog.vue';
import UserTable from './user/UserTable.vue';

const { activeTool, setActiveTool, canAccessPage, canUsePageAction } = useAppContext();

const {
  roles,
  search,
  statusFilter,
  isLoading,
  message,
  messageTone,
  page,
  pageSize,
  dialog,
  resetPasswordUser,
  resetTwoFactorTarget,
  deleteTarget,
  form,
  formErrors,
  resetPassword,
  showPassword,
  columnsOpen,
  fullscreen,
  tableStyle,
  filteredUsers,
  pagedUsers,
  totalPages,
  passwordRules,
  resetPasswordRules,
  passwordMismatch,
  passwordStrength,
  resetPasswordStrength,
  passwordStrengthText,
  resetPasswordStrengthText,
  passwordStrengthClass,
  resetPasswordStrengthClass,
  passwordHint,
  resetPasswordHint,
  primaryRoleId,
  allColumnsVisible,
  someColumnsVisible,
  dialogTitle,
  dialogSubmitText,
  refreshUsers,
  openCreateDialog,
  openEditDialog,
  saveUser,
  toggleUserStatus,
  openResetPassword,
  saveResetPassword,
  enableUserTwoFactor,
  disableUserTwoFactor,
  openResetTwoFactor,
  resetUserTwoFactor,
  toggleUserSessionAudit,
  openDeleteUser,
  deleteUser,
  closeAccountDialog,
  closeResetPasswordDialog,
  closeResetTwoFactorDialog,
  closeDeleteDialog,
  roleNames,
  loginStateText,
  twoFactorStatusClass,
  sessionAuditEnabled,
  openRoleManager,
  openMfaHelp,
  setPage,
  setPageSize,
  isColumnVisible,
  isOnlyVisibleColumn,
  updateColumnVisibility,
  toggleAllColumns,
  resetColumns,
} = useUserManager({ setActiveTool });

const searchDraft = ref('');
const statusDraft = ref<'all' | 'active' | 'disabled'>('all');

function runSearch() {
  search.value = searchDraft.value.trim();
  statusFilter.value = statusDraft.value;
}

function resetSearch() {
  searchDraft.value = '';
  statusDraft.value = 'all';
  search.value = '';
  statusFilter.value = 'all';
}
</script>

<template>
  <section v-if="activeTool === 'users'" class="user-manager-page" :class="{ fullscreen }" @click="columnsOpen = false">
    <template v-if="canAccessPage('users')">
      <SystemSearchPanel>
        <el-form class="system-search-form" inline label-position="left" @submit.prevent="runSearch">
          <el-form-item label="登录账号">
            <el-input v-model="searchDraft" class="system-search-field" placeholder="请输入登录账号或用户名称" clearable @keyup.enter="runSearch" />
          </el-form-item>
          <el-form-item label="账户状态">
            <el-select v-model="statusDraft" class="system-search-field" placeholder="请选择账户状态">
              <el-option label="全部" value="all" />
              <el-option label="正常" value="active" />
              <el-option label="禁用" value="disabled" />
            </el-select>
          </el-form-item>
          <el-form-item class="system-search-actions">
            <el-button type="primary" plain @click="runSearch">
              <AppIcon name="search" :size="16" />
              搜索
            </el-button>
            <el-button type="danger" plain @click="resetSearch">
              <AppIcon name="reset" :size="16" />
              重置
            </el-button>
          </el-form-item>
        </el-form>
      </SystemSearchPanel>

      <article class="user-list-panel">
        <div class="user-list-toolbar">
          <div class="user-list-heading">
            <h2>账户列表</h2>
            <span>共 {{ filteredUsers.length }} 个账户</span>
          </div>
          <div class="user-toolbar-actions">
            <el-button v-if="canUsePageAction('users', 'create')" type="primary" @click="openCreateDialog">
              <AppIcon name="plus" :size="15" />
              <span>新建</span>
            </el-button>
            <span v-if="canUsePageAction('users', 'create')" class="user-toolbar-divider"></span>
            <el-tooltip content="刷新" placement="top">
              <el-button circle @click="refreshUsers">
                <AppIcon name="refresh" :size="18" />
              </el-button>
            </el-tooltip>
            <el-popover
              v-model:visible="columnsOpen"
              placement="bottom-end"
              trigger="click"
              width="220"
              popper-class="user-column-menu"
              @click.stop
            >
              <template #reference>
                <el-button circle @click.stop>
                  <AppIcon name="settings" :size="18" />
                </el-button>
              </template>
              <div class="user-column-menu-head">
                <el-checkbox
                  :model-value="allColumnsVisible"
                  :indeterminate="someColumnsVisible && !allColumnsVisible"
                  @change="toggleAllColumns"
                >
                  列显示
                </el-checkbox>
                <el-button size="small" text type="primary" @click="resetColumns">重置</el-button>
              </div>
              <div class="user-column-options">
                <el-checkbox
                  v-for="column in userColumnOptions"
                  :key="column.key"
                  :model-value="isColumnVisible(column.key)"
                  :disabled="isOnlyVisibleColumn(column.key)"
                  @change="updateColumnVisibility(column.key, $event)"
                >
                  {{ column.label }}
                </el-checkbox>
              </div>
            </el-popover>
            <el-tooltip :content="fullscreen ? '退出全屏' : '全屏'" placement="top">
              <el-button circle @click="fullscreen = !fullscreen">
                <AppIcon :name="fullscreen ? 'minimize' : 'maximize'" :size="18" />
              </el-button>
            </el-tooltip>
          </div>
        </div>

        <p v-if="message" class="user-message" :class="messageTone">{{ message }}</p>

        <UserTable
          :users="pagedUsers"
          :filtered-count="filteredUsers.length"
          :is-loading="isLoading"
          :page="page"
          :page-size="pageSize"
          :total-pages="totalPages"
          :table-style="tableStyle"
          :is-column-visible="isColumnVisible"
          :role-names="roleNames"
          :login-state-text="loginStateText"
          :two-factor-status-class="twoFactorStatusClass"
          :session-audit-enabled="sessionAuditEnabled"
          :can-use-page-action="canUsePageAction"
          @toggle-status="toggleUserStatus"
          @enable-two-factor="enableUserTwoFactor"
          @disable-two-factor="disableUserTwoFactor"
          @reset-two-factor="openResetTwoFactor"
          @toggle-session-audit="toggleUserSessionAudit"
          @edit="openEditDialog"
          @reset-password="openResetPassword"
          @delete="openDeleteUser"
          @update-page="setPage"
          @update-page-size="setPageSize"
        />
      </article>
    </template>
    <div v-else class="permission-empty">暂无用户管理权限</div>

    <UserAccountDialog
      v-if="dialog"
      v-model:form="form"
      v-model:primary-role-id="primaryRoleId"
      v-model:show-password="showPassword"
      :dialog="dialog"
      :roles="roles"
      :title="dialogTitle"
      :submit-text="dialogSubmitText"
      :password-rules="passwordRules"
      :password-strength="passwordStrength"
      :password-strength-class="passwordStrengthClass"
      :password-strength-text="passwordStrengthText"
      :password-hint="passwordHint"
      :password-mismatch="passwordMismatch"
      :form-errors="formErrors"
      :message="message"
      @submit="saveUser"
      @close="closeAccountDialog"
      @open-role-manager="openRoleManager"
      @open-mfa-help="openMfaHelp"
    />

    <UserResetPasswordDialog
      v-if="resetPasswordUser"
      v-model:password="resetPassword"
      :rules="resetPasswordRules"
      :strength="resetPasswordStrength"
      :strength-class="resetPasswordStrengthClass"
      :strength-text="resetPasswordStrengthText"
      :hint="resetPasswordHint"
      @submit="saveResetPassword"
      @close="closeResetPasswordDialog"
    />

    <UserResetTwoFactorDialog
      v-if="resetTwoFactorTarget"
      :user="resetTwoFactorTarget"
      @close="closeResetTwoFactorDialog"
      @confirm="resetUserTwoFactor"
    />

    <UserDeleteDialog
      v-if="deleteTarget"
      :user="deleteTarget"
      @close="closeDeleteDialog"
      @confirm="deleteUser"
    />
  </section>
</template>
