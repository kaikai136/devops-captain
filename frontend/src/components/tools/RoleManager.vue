<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import { apiDelete, apiGet, apiPost, apiPut } from '../../api';
import { useAppContext } from '@app/context';
import { dashboardNavItem, navGroups } from '@app/navigation';
import { errorMessage } from '@shared/utils/errors';
import AppIcon from '@shared/components/AppIcon.vue';
import AppPagination from '@shared/components/AppPagination.vue';

interface SystemRole {
  id: number;
  name: string;
  permissionIds: number[];
  userCount: number;
}

interface SystemUser {
  id: number;
  username: string;
  email: string;
  firstName: string;
  isActive: boolean;
  isBuiltinAdmin?: boolean;
  roleIds: number[];
}

interface SystemPermission {
  id: number;
  codename: string;
  label: string;
  featureKey: string;
  actionKey: string;
  permissionType: 'page' | 'action' | 'other';
  isFeature: boolean;
}

type RoleDialogMode = 'create' | 'edit' | 'view' | 'permissions';

interface RoleForm {
  name: string;
  permissionIds: number[];
}

interface RoleUserPayload {
  role: SystemRole;
  users: SystemUser[];
}

interface PermissionGroup {
  key: string;
  label: string;
  items: typeof navGroups[number]['items'];
}

const { activeTool, canUsePageAction, canUseAnyPageAction } = useAppContext();
const sessionAuditPermissionAlias = { featureKey: 'hosts', actionKey: 'session_audit' } as const;

const roles = ref<SystemRole[]>([]);
const permissions = ref<SystemPermission[]>([]);
const searchDraft = ref('');
const search = ref('');
const page = ref(1);
const pageSize = ref(10);
const isLoading = ref(false);
const message = ref('');
const messageTone = ref<'error' | 'success'>('error');
const columnsOpen = ref(false);
const dialog = ref<{ mode: RoleDialogMode; role: SystemRole | null } | null>(null);
const deleteTarget = ref<SystemRole | null>(null);
const form = ref<RoleForm>(emptyRoleForm());
const roleUserDialog = ref<SystemRole | null>(null);
const roleUsers = ref<SystemUser[]>([]);
const roleUserIds = ref<Set<number>>(new Set());
const isLoadingRoleUsers = ref(false);
const isSavingRoleUsers = ref(false);

const filteredRoles = computed(() => {
  const query = search.value.trim().toLowerCase();
  if (!query) return roles.value;
  return roles.value.filter((role) => [role.name, roleCode(role)].some((value) => value.toLowerCase().includes(query)));
});

const featurePermissions = computed(() => permissions.value.filter((permission) => permission.isFeature && permission.featureKey));
const pagePermissions = computed(() => featurePermissions.value.filter((permission) => permission.permissionType === 'page'));
const actionPermissions = computed(() => featurePermissions.value.filter((permission) => permission.permissionType === 'action'));
const permissionByFeatureKey = computed(() => new Map(pagePermissions.value.map((permission) => [permission.featureKey, permission])));
const actionPermissionsByFeatureKey = computed(() => {
  const groups = new Map<string, SystemPermission[]>();
  actionPermissions.value.forEach((permission) => {
    const current = groups.get(permission.featureKey) ?? [];
    current.push(permission);
    groups.set(permission.featureKey, current);
  });
  return groups;
});
const permissionGroups = computed<PermissionGroup[]>(() => [
  { key: 'dashboard', label: '核心页面', items: [dashboardNavItem] },
  ...navGroups,
]);
const totalPages = computed(() => Math.max(1, Math.ceil(filteredRoles.value.length / pageSize.value)));
const pagedRoles = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  return filteredRoles.value.slice(start, start + pageSize.value);
});

onMounted(loadRoles);

watch([search, pageSize], () => {
  page.value = 1;
});

watch(totalPages, (next) => {
  if (page.value > next) page.value = next;
});

async function loadRoles() {
  isLoading.value = true;
  clearMessage();
  try {
    const [roleData, permissionData] = await Promise.all([
      apiGet<SystemRole[]>('/api/system/roles/'),
      apiGet<SystemPermission[]>('/api/system/permissions/'),
    ]);
    roles.value = roleData;
    permissions.value = permissionData;
  } catch (error) {
    roles.value = [];
    permissions.value = [];
    setError(errorMessage(error));
  } finally {
    isLoading.value = false;
  }
}

function runSearch() {
  search.value = searchDraft.value.trim();
}

function resetSearch() {
  searchDraft.value = '';
  search.value = '';
}

function openCreateDialog() {
  clearMessage();
  form.value = emptyRoleForm();
  dialog.value = { mode: 'create', role: null };
}

function openViewDialog(role: SystemRole) {
  form.value = { name: role.name, permissionIds: roleFeaturePermissionIds(role) };
  dialog.value = { mode: 'view', role };
}

function openEditDialog(role: SystemRole) {
  clearMessage();
  form.value = { name: role.name, permissionIds: roleFeaturePermissionIds(role) };
  dialog.value = { mode: 'edit', role };
}

function openPermissionDialog(role: SystemRole) {
  clearMessage();
  form.value = { name: role.name, permissionIds: roleFeaturePermissionIds(role) };
  dialog.value = { mode: 'permissions', role };
}

async function openRoleUserDialog(role: SystemRole) {
  if (!canUsePageAction('roles', 'edit')) return;
  clearMessage();
  roleUserDialog.value = role;
  roleUsers.value = [];
  roleUserIds.value = new Set();
  isLoadingRoleUsers.value = true;
  try {
    const payload = await apiGet<RoleUserPayload>(`/api/system/roles/${role.id}/users/`);
    replaceRole(payload.role);
    roleUserDialog.value = payload.role;
    roleUsers.value = payload.users;
    roleUserIds.value = new Set(payload.users.filter((user) => !user.isBuiltinAdmin && user.roleIds.includes(role.id)).map((user) => user.id));
  } catch (error) {
    setError(errorMessage(error));
    roleUserDialog.value = null;
  } finally {
    isLoadingRoleUsers.value = false;
  }
}

function closeRoleUserDialog() {
  roleUserDialog.value = null;
  roleUsers.value = [];
  roleUserIds.value = new Set();
}

function toggleRoleUser(user: SystemUser, checked: boolean | string | number) {
  if (user.isBuiltinAdmin) return;
  const next = new Set(roleUserIds.value);
  if (Boolean(checked)) {
    next.add(user.id);
  } else {
    next.delete(user.id);
  }
  roleUserIds.value = next;
}

async function saveRoleUsers() {
  const role = roleUserDialog.value;
  if (!role || isSavingRoleUsers.value) return;
  isSavingRoleUsers.value = true;
  clearMessage();
  try {
    const payload = await apiPut<RoleUserPayload>(`/api/system/roles/${role.id}/users/`, { userIds: [...roleUserIds.value] });
    replaceRole(payload.role);
    closeRoleUserDialog();
    await loadRoles();
    setSuccess('角色用户已保存');
  } catch (error) {
    setError(errorMessage(error));
  } finally {
    isSavingRoleUsers.value = false;
  }
}

async function saveRole() {
  const currentDialog = dialog.value;
  if (!currentDialog || currentDialog.mode === 'view') return;
  clearMessage();
  const payload = {
    name: form.value.name.trim(),
    permissionIds: form.value.permissionIds,
  };
  if (!payload.name) {
    setError('请输入角色名称');
    return;
  }

  try {
    const saved =
      currentDialog.mode === 'create'
        ? await apiPost<SystemRole>('/api/system/roles/', payload)
        : await apiPut<SystemRole>(`/api/system/roles/${currentDialog.role?.id}/`, payload);
    replaceRole(saved);
    dialog.value = null;
    setSuccess(currentDialog.mode === 'permissions' ? '权限已保存' : '角色已保存');
  } catch (error) {
    setError(errorMessage(error));
  }
}

async function deleteRole() {
  if (!deleteTarget.value) return;
  clearMessage();
  try {
    const roleId = deleteTarget.value.id;
    await apiDelete(`/api/system/roles/${roleId}/`);
    roles.value = roles.value.filter((role) => role.id !== roleId);
    deleteTarget.value = null;
    setSuccess('角色已删除');
  } catch (error) {
    setError(errorMessage(error));
  }
}

function isFeatureChecked(featureKey: string) {
  const virtualPermission = virtualPageActionPermission(featureKey);
  if (virtualPermission) return form.value.permissionIds.includes(virtualPermission.id);
  const permission = permissionByFeatureKey.value.get(featureKey);
  return Boolean(permission && form.value.permissionIds.includes(permission.id));
}

function setFeatureChecked(featureKey: string, checked: boolean) {
  const virtualPermission = virtualPageActionPermission(featureKey);
  if (virtualPermission) {
    const next = new Set(form.value.permissionIds);
    if (checked) {
      next.add(virtualPermission.id);
    } else {
      next.delete(virtualPermission.id);
    }
    form.value.permissionIds = [...next].sort((a, b) => a - b);
    return;
  }
  const permission = permissionByFeatureKey.value.get(featureKey);
  const actionPermissions = visiblePageActionPermissions(featureKey);
  if (!permission && !actionPermissions.length) return;
  const next = new Set(form.value.permissionIds);
  if (checked) {
    if (permission) next.add(permission.id);
    actionPermissions.forEach((actionPermission) => next.add(actionPermission.id));
  } else {
    if (permission) next.delete(permission.id);
    actionPermissions.forEach((actionPermission) => next.delete(actionPermission.id));
  }
  form.value.permissionIds = [...next].sort((a, b) => a - b);
}

function toggleFeature(featureKey: string, checked: boolean | string | number) {
  setFeatureChecked(featureKey, Boolean(checked));
}

function groupFeatureKeys(groupKey: string) {
  return permissionGroups.value.find((group) => group.key === groupKey)?.items.map((item) => item.key) ?? [];
}

function featurePermissionIds(featureKey: string) {
  const ids = [];
  const virtualPermission = virtualPageActionPermission(featureKey);
  if (virtualPermission) return [virtualPermission.id];
  const pagePermission = permissionByFeatureKey.value.get(featureKey);
  if (pagePermission) ids.push(pagePermission.id);
  visiblePageActionPermissions(featureKey).forEach((permission) => ids.push(permission.id));
  return ids;
}

function groupPermissionIds(groupKey: string) {
  return groupFeatureKeys(groupKey).flatMap((featureKey) => featurePermissionIds(featureKey));
}

function isGroupChecked(groupKey: string) {
  const ids = groupPermissionIds(groupKey);
  return ids.length > 0 && ids.every((id) => form.value.permissionIds.includes(id));
}

function isGroupPartial(groupKey: string) {
  const ids = groupPermissionIds(groupKey);
  const checkedCount = ids.filter((id) => form.value.permissionIds.includes(id)).length;
  return checkedCount > 0 && checkedCount < ids.length;
}

function toggleGroup(groupKey: string, checked: boolean | string | number) {
  const next = new Set(form.value.permissionIds);
  groupPermissionIds(groupKey).forEach((id) => {
    if (Boolean(checked)) {
      next.add(id);
    } else {
      next.delete(id);
    }
  });
  form.value.permissionIds = [...next].sort((a, b) => a - b);
}

function isFeaturePartial(featureKey: string) {
  const ids = featurePermissionIds(featureKey);
  const checkedCount = ids.filter((id) => form.value.permissionIds.includes(id)).length;
  return checkedCount > 0 && checkedCount < ids.length;
}

function isActionChecked(permissionId: number) {
  return form.value.permissionIds.includes(permissionId);
}

function setActionChecked(featureKey: string, permissionId: number, checked: boolean) {
  const next = new Set(form.value.permissionIds);
  if (checked) {
    const pagePermission = permissionByFeatureKey.value.get(featureKey);
    if (pagePermission) next.add(pagePermission.id);
    next.add(permissionId);
  } else {
    next.delete(permissionId);
  }
  form.value.permissionIds = [...next].sort((a, b) => a - b);
}

function toggleAction(featureKey: string, permissionId: number, checked: boolean | string | number) {
  setActionChecked(featureKey, permissionId, Boolean(checked));
}

function pageActionPermissions(featureKey: string) {
  const virtualPermission = virtualPageActionPermission(featureKey);
  if (virtualPermission) return [virtualPermission];
  return visiblePageActionPermissions(featureKey);
}

function visiblePageActionPermissions(featureKey: string) {
  const permissions = actionPermissionsByFeatureKey.value.get(featureKey) ?? [];
  if (featureKey === sessionAuditPermissionAlias.featureKey) {
    return permissions.filter((permission) => permission.actionKey !== sessionAuditPermissionAlias.actionKey);
  }
  return permissions;
}

function virtualPageActionPermission(featureKey: string) {
  if (featureKey !== 'sessionAudits') return null;
  return (
    actionPermissionsByFeatureKey.value
      .get(sessionAuditPermissionAlias.featureKey)
      ?.find((permission) => permission.actionKey === sessionAuditPermissionAlias.actionKey) ?? null
  );
}

function displayPermissionLabel(permission: SystemPermission) {
  const parts = permission.label.split('：');
  return parts[1] || permission.label.replace(/^访问/, '');
}

function setPage(nextPage: number) {
  page.value = Math.min(Math.max(1, nextPage), totalPages.value);
}

function setPageSize(nextPageSize: number) {
  pageSize.value = nextPageSize;
}

function roleCode(role: SystemRole) {
  if (/管理员|admin/i.test(role.name)) return 'admin';
  if (/普通|用户|user/i.test(role.name)) return 'user';
  const normalized = role.name
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '');
  return normalized || `role-${role.id}`;
}

function permissionText(role: SystemRole) {
  const ids = new Set(roleFeaturePermissionIds(role));
  const pageCount = pagePermissions.value.filter((permission) => ids.has(permission.id)).length;
  const actionCount = actionPermissions.value.filter((permission) => ids.has(permission.id)).length;
  return `${pageCount} 个页面 / ${actionCount} 项功能`;
}

function userRoleText(user: SystemUser) {
  const roleNameById = new Map(roles.value.map((role) => [role.id, role.name]));
  const names = user.roleIds.map((roleId) => roleNameById.get(roleId)).filter(Boolean);
  return names.length ? names.join('、') : '暂无角色';
}

function roleFeaturePermissionIds(role: SystemRole) {
  const featureIds = new Set(featurePermissions.value.map((permission) => permission.id));
  return role.permissionIds.filter((permissionId) => featureIds.has(permissionId));
}

function dialogTitle() {
  if (!dialog.value) return '';
  const titles: Record<RoleDialogMode, string> = {
    create: '新增角色',
    edit: '编辑角色',
    view: '查看角色',
    permissions: '权限管理',
  };
  return titles[dialog.value.mode];
}

function closeDialog() {
  dialog.value = null;
}

function clearMessage() {
  message.value = '';
  messageTone.value = 'error';
}

function setError(value: string) {
  messageTone.value = 'error';
  message.value = value;
}

function setSuccess(value: string) {
  messageTone.value = 'success';
  message.value = value;
}

function replaceRole(role: SystemRole) {
  const index = roles.value.findIndex((item) => item.id === role.id);
  if (index >= 0) {
    roles.value.splice(index, 1, role);
  } else {
    roles.value.push(role);
  }
}

function emptyRoleForm(): RoleForm {
  return {
    name: '',
    permissionIds: [],
  };
}
</script>

<template>
  <section v-if="activeTool === 'roles'" class="role-manager-page" @click="columnsOpen = false">
    <template v-if="canUseAnyPageAction('roles', ['create', 'edit', 'permissions', 'delete'])">
      <article class="role-list-panel">
        <div class="role-list-toolbar">
          <div class="role-list-heading">
            <h2>角色与权限</h2>
            <span>共 {{ filteredRoles.length }} 个角色</span>
          </div>
          <div class="role-toolbar-actions">
            <el-input
              v-model="searchDraft"
              class="role-toolbar-search"
              placeholder="搜索角色名称或标识"
              clearable
              @input="runSearch"
              @clear="resetSearch"
              @keyup.enter="runSearch"
            >
              <template #prefix>
                <AppIcon name="search" :size="15" />
              </template>
            </el-input>
            <el-button v-if="canUsePageAction('roles', 'create')" type="primary" @click="openCreateDialog">
              <AppIcon name="circlePlus" :size="15" />
              <span>新增角色</span>
            </el-button>
            <span class="role-toolbar-divider"></span>
            <el-tooltip content="刷新" placement="top">
              <el-button circle @click="loadRoles"><AppIcon name="refresh" :size="18" /></el-button>
            </el-tooltip>
            <el-popover v-model:visible="columnsOpen" placement="bottom-end" trigger="click" width="190" popper-class="role-column-menu">
              <template #reference>
                <el-button circle @click.stop><AppIcon name="settings" :size="18" /></el-button>
              </template>
              <span>当前表格列固定展示</span>
            </el-popover>
          </div>
        </div>

        <p v-if="message" class="role-message" :class="messageTone">{{ message }}</p>

        <el-table :data="pagedRoles" row-key="id" class="role-table app-data-table" v-loading="isLoading" empty-text="暂无角色数据">
          <el-table-column type="index" label="序号" width="76" :index="(index) => (page - 1) * pageSize + index + 1" />
          <el-table-column prop="name" label="角色名称" min-width="150" />
          <el-table-column label="角色标识" min-width="130">
            <template #default="{ row }">{{ roleCode(row) }}</template>
          </el-table-column>
          <el-table-column label="状态" min-width="100">
            <template #default>
              <el-tag type="success" size="small" effect="dark">启用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="用户数据" min-width="150">
            <template #default="{ row }">
              <el-button v-if="canUsePageAction('roles', 'edit')" text type="primary" @click.stop="openRoleUserDialog(row)">
                {{ row.userCount ?? 0 }} 个用户
              </el-button>
              <span v-else>{{ row.userCount ?? 0 }} 个用户</span>
            </template>
          </el-table-column>
          <el-table-column label="权限管理" min-width="140">
            <template #default="{ row }">
              <el-button v-if="canUsePageAction('roles', 'permissions')" text type="primary" :title="permissionText(row)" @click="openPermissionDialog(row)">
                管理
              </el-button>
              <span v-else class="role-action-placeholder">-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" min-width="230" fixed="right">
            <template #default="{ row }">
              <div class="role-row-actions">
                <el-button size="small" @click="openViewDialog(row)"><AppIcon name="eye" :size="13" />查看</el-button>
                <el-button v-if="canUsePageAction('roles', 'edit')" size="small" type="primary" @click="openEditDialog(row)">
                  <AppIcon name="edit" :size="13" />编辑
                </el-button>
                <el-button v-if="canUsePageAction('roles', 'delete')" size="small" type="danger" @click="deleteTarget = row">
                  <AppIcon name="trash" :size="13" />删除
                </el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <div class="host-pagination" aria-label="角色列表分页">
          <AppPagination
            :page="page"
            :page-size="pageSize"
            :total="filteredRoles.length"
            @page-change="setPage"
            @page-size-change="setPageSize"
          />
        </div>
      </article>
    </template>
    <div v-else class="permission-empty">暂无可用功能</div>

    <el-dialog
      :model-value="dialog !== null"
      :title="dialogTitle()"
      :width="dialog?.mode === 'permissions' || dialog?.mode === 'view' ? '880px' : '520px'"
      class="role-form-dialog role-popup-dialog"
      :class="{ 'role-permission-dialog': dialog?.mode === 'permissions' || dialog?.mode === 'view' }"
      :close-on-click-modal="false"
      @update:model-value="(visible) => { if (!visible) closeDialog(); }"
    >
      <el-form :model="form" label-position="top" class="popup-body popup-form-grid" @submit.prevent="saveRole">
        <template v-if="dialog">
          <el-form-item v-if="dialog.mode !== 'permissions'" label="角色名称" required>
            <el-input v-model="form.name" :readonly="dialog.mode === 'view'" placeholder="请输入角色名称" />
          </el-form-item>
          <el-form-item v-if="dialog.mode !== 'create' && dialog.mode !== 'permissions'" label="角色标识">
            <el-input :model-value="dialog.role ? roleCode(dialog.role) : ''" readonly />
          </el-form-item>
          <el-form-item v-if="dialog.mode !== 'create' && dialog.mode !== 'permissions'" label="状态">
            <el-input model-value="启用" readonly />
          </el-form-item>

          <div v-if="dialog.mode === 'permissions' || dialog.mode === 'view'" class="role-feature-permissions">
            <div class="role-permission-summary">
              <span class="role-permission-summary-icon" aria-hidden="true">
                <AppIcon name="shield" :size="19" />
              </span>
              <div>
                <strong>{{ dialog.mode === 'view' ? '角色权限详情' : '配置角色权限' }}</strong>
                <span>{{ dialog.role?.name || form.name }}</span>
              </div>
              <em>已选择 {{ form.permissionIds.length }} 项</em>
            </div>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              title="页面权限控制左侧菜单入口，功能权限控制页面内可用操作。权限变更后，属于该角色的账号重新登录后生效。"
            />

            <div class="role-permission-table-wrap">
              <table class="role-permission-table app-native-data-table">
                <colgroup>
                  <col class="role-permission-module-column" />
                  <col class="role-permission-page-column" />
                  <col />
                </colgroup>
                <thead>
                  <tr>
                    <th scope="col">模块</th>
                    <th scope="col">页面</th>
                    <th scope="col">功能权限</th>
                  </tr>
                </thead>
                <tbody v-for="group in permissionGroups" :key="group.key">
                  <tr v-for="(item, itemIndex) in group.items" :key="item.key">
                    <th v-if="itemIndex === 0" class="role-permission-module-cell" scope="rowgroup" :rowspan="group.items.length">
                      <el-checkbox
                        :model-value="isGroupChecked(group.key)"
                        :indeterminate="isGroupPartial(group.key)"
                        :disabled="dialog.mode === 'view'"
                        @change="toggleGroup(group.key, $event)"
                      >
                        {{ group.label }}
                      </el-checkbox>
                    </th>
                    <td class="role-permission-page-cell">
                      <el-checkbox
                        :model-value="isFeatureChecked(item.key)"
                        :indeterminate="isFeaturePartial(item.key)"
                        :disabled="dialog.mode === 'view'"
                        @change="toggleFeature(item.key, $event)"
                      >
                        {{ item.label }}
                      </el-checkbox>
                    </td>
                    <td class="role-permission-actions-cell">
                      <div class="role-permission-actions">
                        <el-checkbox
                          v-for="permission in pageActionPermissions(item.key)"
                          :key="permission.id"
                          :model-value="isActionChecked(permission.id)"
                          :disabled="dialog.mode === 'view'"
                          @change="toggleAction(item.key, permission.id, $event)"
                        >
                          {{ displayPermissionLabel(permission) }}
                        </el-checkbox>
                        <span v-if="!pageActionPermissions(item.key).length" class="role-action-empty">暂无可配置功能</span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="closeDialog">取消</el-button>
        <el-button v-if="dialog?.mode !== 'view'" type="primary" @click="saveRole">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog
      :model-value="roleUserDialog !== null"
      title="调整权限用户"
      width="640px"
      class="role-form-dialog role-popup-dialog"
      :close-on-click-modal="false"
      @update:model-value="(visible) => { if (!visible) closeRoleUserDialog(); }"
    >
      <p v-if="roleUserDialog" class="role-user-dialog-subtitle">为角色“{{ roleUserDialog.name }}”选择绑定用户，保存后用户重新登录生效。</p>
      <div v-loading="isLoadingRoleUsers" class="role-user-picker popup-body">
        <el-checkbox
          v-for="user in roleUsers"
          :key="user.id"
          class="role-user-option"
          :model-value="roleUserIds.has(user.id)"
          :disabled="user.isBuiltinAdmin"
          @change="toggleRoleUser(user, $event)"
        >
          <span>
            <strong>{{ user.firstName || user.username }}</strong>
            <em>{{ user.username }}{{ user.email ? ` / ${user.email}` : '' }}</em>
            <small>当前角色：{{ userRoleText(user) }}</small>
          </span>
          <el-tag :type="user.isActive ? 'success' : 'danger'" size="small" effect="dark">{{ user.isActive ? '启用' : '停用' }}</el-tag>
        </el-checkbox>
        <el-empty v-if="!isLoadingRoleUsers && !roleUsers.length" description="暂无用户数据" />
      </div>
      <template #footer>
        <div class="popup-actions">
          <span class="role-user-selected">已选择 {{ roleUserIds.size }} 个用户</span>
          <el-button @click="closeRoleUserDialog">取消</el-button>
          <el-button type="primary" :disabled="isLoadingRoleUsers || isSavingRoleUsers" :loading="isSavingRoleUsers" @click="saveRoleUsers">
            保存
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      :model-value="deleteTarget !== null"
      title="删除角色"
      width="420px"
      class="role-form-dialog role-popup-dialog"
      :close-on-click-modal="false"
      @update:model-value="(visible) => { if (!visible) deleteTarget = null; }"
    >
      <p class="popup-body popup-danger">确定删除角色“{{ deleteTarget?.name }}”吗？</p>
      <template #footer>
        <div class="popup-actions">
          <el-button @click="deleteTarget = null">取消</el-button>
          <el-button type="danger" @click="deleteRole">删除</el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>
