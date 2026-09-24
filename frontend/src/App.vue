<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, provide, ref, watch } from 'vue';

import { appContextKey } from '@app/context';
import AppIcon from '@shared/components/AppIcon.vue';
import HostExportDialog from '@features/hosts/components/HostExportDialog.vue';
import HostImportDialog from '@features/hosts/components/HostImportDialog.vue';
import WatermarkOverlay from '@shared/components/WatermarkOverlay.vue';
import LockScreenOverlay from '@shared/components/LockScreenOverlay.vue';
import UserAvatar from '@shared/components/UserAvatar.vue';
import { hostExportColumnOptions, type HostExportColumnKey, type HostExportScope } from './composables/features/useHostManager';
import { useAppState } from './composables/useAppState';
import { errorMessage } from '@shared/utils/errors';
import type { ToolKey } from './types';

type DashboardPageExpose = {
  refresh?: () => Promise<void> | void;
};

const AccountManager = defineAsyncComponent(() => import('./components/tools/AccountManager.vue'));
const AuthenticatorPanel = defineAsyncComponent(() => import('./components/tools/AuthenticatorPanel.vue'));
const BulkExecutionPanel = defineAsyncComponent(() => import('./features/bulk-execution/components/BulkExecutionPanel.vue'));
const ApplicationMarketPanel = defineAsyncComponent(() => import('./features/application-market/components/ApplicationMarketPanel.vue'));
const DashboardPage = defineAsyncComponent(() => import('./components/tools/DashboardPage.vue'));
const DeviceManager = defineAsyncComponent(() => import('./features/company/components/DeviceManager.vue'));
const HostManager = defineAsyncComponent(() => import('./components/tools/HostManager.vue'));
const IpScanner = defineAsyncComponent(() => import('./components/tools/IpScanner.vue'));
const SessionAuditManager = defineAsyncComponent(() => import('./components/tools/SessionAuditManager.vue'));
const LoginLogManager = defineAsyncComponent(() => import('./components/tools/LoginLogManager.vue'));
const LoginPage = defineAsyncComponent(() => import('./components/auth/LoginPage.vue'));
const MachineProbe = defineAsyncComponent(() => import('./components/tools/MachineProbe.vue'));
const OperationLogManager = defineAsyncComponent(() => import('./components/tools/OperationLogManager.vue'));
const PasswordGenerator = defineAsyncComponent(() => import('./components/tools/PasswordGenerator.vue'));
const ProfileCenter = defineAsyncComponent(() => import('./components/tools/ProfileCenter.vue'));
const RoleManager = defineAsyncComponent(() => import('./components/tools/RoleManager.vue'));
const SecurityScanPanel = defineAsyncComponent(() => import('./components/tools/SecurityScanPanel.vue'));
const SubnetCalculator = defineAsyncComponent(() => import('./components/tools/SubnetCalculator.vue'));
const SystemSettingsPanel = defineAsyncComponent(() => import('./components/tools/SystemSettingsPanel.vue'));
const UserManager = defineAsyncComponent(() => import('./components/tools/UserManager.vue'));

const appState = useAppState();
provide(appContextKey, appState);

const hostExportScope = ref<HostExportScope>('all');
const selectedHostExportColumns = ref<Set<HostExportColumnKey>>(new Set(hostExportColumnOptions.map((column) => column.field)));
const selectedHostExportColumnList = computed(() => [...selectedHostExportColumns.value]);
const allHostExportColumnsSelected = computed(() => selectedHostExportColumns.value.size === hostExportColumnOptions.length);
const dashboardPageRef = ref<DashboardPageExpose | null>(null);
const isDashboardRefreshing = ref(false);

const {
  activeTool,
  groupsOpen,
  sidebarCollapsed,
  hoveredNavGroup,
  isWorkspaceDark,
  localIp,
  selectedHost,
  ipScanMessage,
  dashboardNavItem,
  navGroups,
  activeNavGroup,
  activeNavItem,
  currentUser,
  isLocked,
  hasWorkspaceDataLoaded,
  canAccessPage,
  canUsePageAction,
  isAuthReady,
  isAuthenticated,
  login,
  verifyTwoFactorLogin,
  verifyTwoFactorSetupLogin,
  logout,
  lockSession,
  unlockSession,
  showToast,
  shouldShowWatermark,
  siteIdentity,
  layoutFooter,
  renderSystemTemplate,
  watermarkText,
  setActiveTool,
  selectNavItem,
  toggleSidebar,
  toggleWorkspaceTheme,
  openNavFlyout,
  closeNavFlyout,
  navItemIcon,
  navGroupIcon,
  saveAuthEntries,
  triggerAuthImportFile,
  authImportFile,
  importAuthEntries,
  exportPasswordRecords,
  triggerPasswordImportFile,
  passwordImportFile,
  importPasswordRecords,
  hostImportFile,
  hostImportAccept,
  hostTransferDialog,
  hostTransferFormat,
  openHostTransferDialog,
  closeHostTransferDialog,
  confirmHostTransfer,
  downloadHostImportTemplate,
  backupHostManagement,
  exportHostManagement,
  importHostManagement,
  triggerHostRestoreFile,
  selectedManagedHostIds,
  visibleManagedHosts,
  openWebTerminal,
  useSelectedIpForPing,
  qrPreview,
  copyText,
} = appState;

const selectedManagedHostCount = computed(() => visibleManagedHosts.value.filter((host) => selectedManagedHostIds.value.has(host.id)).length);
const currentUserDisplayName = computed(() => currentUser.value?.displayName || currentUser.value?.first_name || currentUser.value?.username || '未命名用户');
const currentUserAccount = computed(() => currentUser.value?.username || currentUser.value?.email || '当前账户');
const currentUserAvatar = computed(() => currentUser.value?.avatarUrl || '');
const sidebarLogoUrl = computed(() => siteIdentity.value.logoImageUrl || siteIdentity.value.iconUrl);
const footerText = computed(() => renderSystemTemplate(layoutFooter.value.textTemplate));
const footerLinkText = computed(() => renderSystemTemplate(layoutFooter.value.linkText));
const footerStyle = computed(() => ({ fontSize: `${layoutFooter.value.fontSize}px`, color: layoutFooter.value.color }));
const isExternalFooterLink = computed(() => /^https?:\/\//i.test(layoutFooter.value.linkUrl));
const sidebarNow = ref(new Date());
const sidebarClockDate = computed(() => {
  const now = sidebarNow.value;
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  const weekday = new Intl.DateTimeFormat('zh-CN', { weekday: 'long' }).format(now);
  return `${year}-${month}-${day} ${weekday}`;
});
const sidebarClockTime = computed(() =>
  new Intl.DateTimeFormat('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(sidebarNow.value),
);
const breadcrumbItems = computed(() =>
  activeTool.value === 'dashboard'
    ? [
        { key: 'home', label: '首页' },
        { key: 'dashboard', label: dashboardNavItem.value?.label ?? '仪表盘' },
      ]
    : [
        { key: 'home', label: '首页' },
        { key: activeNavGroup.value.key, label: activeNavGroup.value.label },
        { key: activeNavItem.value.key, label: activeNavItem.value.label },
      ],
);

let sidebarClockTimer: number | undefined;

function updateSidebarClock() {
  sidebarNow.value = new Date();
}

onMounted(() => {
  updateSidebarClock();
  sidebarClockTimer = window.setInterval(updateSidebarClock, 1000);
});

onUnmounted(() => {
  if (sidebarClockTimer !== undefined) window.clearInterval(sidebarClockTimer);
});

watch(hostTransferDialog, (mode) => {
  if (mode !== 'export') return;
  hostExportScope.value = 'all';
  selectedHostExportColumns.value = new Set(hostExportColumnOptions.map((column) => column.field));
});

watch(
  [isAuthenticated, isWorkspaceDark],
  ([authenticated, dark]) => {
    if (authenticated) document.documentElement.classList.toggle('dark', dark);
  },
  { immediate: true },
);

function toggleHostExportColumn(column: HostExportColumnKey, event: Event) {
  const checked = (event.target as HTMLInputElement).checked;
  const next = new Set(selectedHostExportColumns.value);
  if (checked) {
    next.add(column);
  } else {
    next.delete(column);
  }
  selectedHostExportColumns.value = next;
}

function toggleAllHostExportColumns(event: Event) {
  const checked = (event.target as HTMLInputElement).checked;
  selectedHostExportColumns.value = checked ? new Set(hostExportColumnOptions.map((column) => column.field)) : new Set();
}

async function confirmHostExport() {
  const exported = await exportHostManagement(hostTransferFormat.value, {
    scope: hostExportScope.value,
    selectedIds: [...selectedManagedHostIds.value],
    columns: selectedHostExportColumnList.value,
  });
  if (exported) closeHostTransferDialog();
}

async function refreshDashboard() {
  if (isDashboardRefreshing.value) return;
  isDashboardRefreshing.value = true;
  try {
    const refresh = dashboardPageRef.value?.refresh;
    if (refresh) await refresh();
    showToast('刷新完成', '仪表盘数据已更新。');
  } finally {
    isDashboardRefreshing.value = false;
  }
}

async function lockCurrentSession() {
  try {
    await lockSession();
  } catch (error) {
    showToast('锁屏失败', errorMessage(error));
  }
}

function handleSidebarSelect(index: string) {
  if (index === 'dashboard') {
    setActiveTool('dashboard');
    return;
  }
  selectNavItem(index as ToolKey);
}

function handleUserCommand(command: 'profile' | 'lock' | 'logout') {
  if (command === 'profile') {
    if (canAccessPage('profile')) setActiveTool('profile');
    return;
  }
  if (command === 'lock') {
    void lockCurrentSession();
    return;
  }
  void logout();
}

function handleFloatAction(command: 'theme' | 'refresh' | 'top') {
  if (command === 'theme') {
    toggleWorkspaceTheme();
    return;
  }
  if (command === 'refresh') {
    void refreshDashboard();
    return;
  }
  window.scrollTo({ top: 0, behavior: 'smooth' });
}
</script>
<template>
  <main v-if="!isAuthReady" class="auth-loading">
    <div>
      <span></span>
      <strong>正在检查登录状态</strong>
    </div>
  </main>
  <LoginPage
    v-else-if="!isAuthenticated"
    :login="login"
    :verify-two-factor-login="verifyTwoFactorLogin"
    :verify-two-factor-setup-login="verifyTwoFactorSetupLogin"
  />
  <main v-else class="app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed, 'workspace-dark': isWorkspaceDark }">
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="sidebar-brand">
        <img :src="sidebarLogoUrl" :alt="siteIdentity.appName" />
        <button
          class="sidebar-brand-toggle"
          type="button"
          :title="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'"
          :aria-label="sidebarCollapsed ? '展开侧边栏' : '折叠侧边栏'"
          :aria-expanded="!sidebarCollapsed"
          @click="toggleSidebar"
        >
          <AppIcon name="chevronRight" :size="16" />
        </button>
      </div>

      <nav class="sidebar-nav">
        <el-scrollbar class="sidebar-scroll">
          <el-menu
            class="workspace-nav-menu"
            :collapse="sidebarCollapsed"
            :collapse-transition="false"
            :default-active="activeTool"
            :ellipsis="false"
            :unique-opened="true"
            @select="handleSidebarSelect"
          >
            <el-menu-item v-if="dashboardNavItem" index="dashboard">
              <AppIcon name="dashboard" :size="18" />
              <span>{{ dashboardNavItem.label }}</span>
            </el-menu-item>
            <el-sub-menu v-for="group in navGroups" :key="group.key" :index="group.key" popper-class="workspace-nav-popper">
              <template #title>
                <AppIcon :name="navGroupIcon(group.key)" :size="18" />
                <span>{{ group.label }}</span>
              </template>
              <el-menu-item v-for="item in group.items" :key="item.key" :index="item.key">
                <AppIcon :name="navItemIcon(item.key)" :size="18" />
                <span>{{ item.label }}</span>
              </el-menu-item>
            </el-sub-menu>
          </el-menu>
        </el-scrollbar>
      </nav>

      <div class="sidebar-clock" aria-label="当前日期和时间">
        <span class="sidebar-clock-label">当前时间</span>
        <strong class="sidebar-clock-time">{{ sidebarClockTime }}</strong>
        <span class="sidebar-clock-date">{{ sidebarClockDate }}</span>
      </div>

    </aside>

    <section class="workspace" :class="{ 'has-workspace-footer': layoutFooter.enabled }">
      <header class="workspace-topbar">
        <div class="workspace-topbar-main">
          <el-breadcrumb class="page-breadcrumb" separator="/">
            <el-breadcrumb-item v-for="(item, index) in breadcrumbItems" :key="item.key">
              <strong v-if="index === breadcrumbItems.length - 1">{{ item.label }}</strong>
              <span v-else>{{ item.label }}</span>
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div class="workspace-actions">
          <div class="header-stats">
            <template v-if="activeTool === 'auth'">
              <el-button v-if="canUsePageAction('auth', 'export')" class="header-action" size="small" plain @click="saveAuthEntries">导出</el-button>
              <el-button v-if="canUsePageAction('auth', 'import')" class="header-action" size="small" plain @click="triggerAuthImportFile">导入</el-button>
              <input ref="authImportFile" hidden type="file" accept="application/json,.json" @change="importAuthEntries" />
            </template>
            <template v-else-if="activeTool === 'password'">
              <el-button v-if="canUsePageAction('password', 'export')" class="header-action" size="small" plain @click="exportPasswordRecords">导出</el-button>
              <el-button v-if="canUsePageAction('password', 'import')" class="header-action" size="small" plain @click="triggerPasswordImportFile">导入</el-button>
              <input ref="passwordImportFile" hidden type="file" accept="text/plain,application/json,.txt,.json" @change="importPasswordRecords" />
            </template>
            <template v-else-if="activeTool === 'hosts'">
              <el-button v-if="canUsePageAction('hosts', 'export')" class="header-action" size="small" plain @click="backupHostManagement">
                <AppIcon name="download" :size="16" />
                <span>备份</span>
              </el-button>
              <el-button v-if="canUsePageAction('hosts', 'import')" class="header-action" size="small" plain @click="triggerHostRestoreFile">
                <AppIcon name="upload" :size="16" />
                <span>恢复</span>
              </el-button>
              <input ref="hostImportFile" hidden type="file" :accept="hostImportAccept" @change="importHostManagement" />
              <el-button
                v-if="canUsePageAction('hosts', 'terminal')"
                class="header-action terminal-action terminal-icon-action"
                circle
                title="Web 终端"
                aria-label="Web 终端"
                @click="openWebTerminal()"
              >
                <AppIcon name="terminal" :size="20" />
              </el-button>
            </template>
            <template v-else-if="activeTool === 'ip' && ipScanMessage">
              <span class="inline-status">{{ ipScanMessage }}</span>
            </template>
            <template v-else-if="activeTool === 'dashboard' || activeTool === 'sessionAudits' || activeTool === 'bulkExecution' || activeTool === 'applicationMarket' || activeTool === 'accounts' || activeTool === 'companyDevices' || activeTool === 'users' || activeTool === 'loginLogs' || activeTool === 'operationLogs' || activeTool === 'roles' || activeTool === 'profile' || activeTool === 'systemSettings' || activeTool === 'securityScan'"></template>
            <template v-else>
              <article><span>本机 IP</span><strong>{{ localIp }}</strong></article>
              <article class="selected-host-card" title="双击使用选中 IP" @dblclick="useSelectedIpForPing">
                <span>选中 IP</span>
                <strong>{{ selectedHost }}</strong>
              </article>
            </template>
          </div>
          <el-button
            class="workspace-icon-button workspace-theme-toggle"
            circle
            :title="isWorkspaceDark ? '切换明亮模式' : '切换暗黑模式'"
            :aria-label="isWorkspaceDark ? '切换明亮模式' : '切换暗黑模式'"
            :aria-pressed="isWorkspaceDark"
            @click="toggleWorkspaceTheme"
          >
            <AppIcon :name="isWorkspaceDark ? 'sun' : 'moon'" :size="18" />
          </el-button>
          <el-button
            v-if="activeTool === 'dashboard'"
            class="workspace-icon-button workspace-dashboard-refresh"
            circle
            :loading="isDashboardRefreshing"
            :disabled="isDashboardRefreshing"
            :title="isDashboardRefreshing ? '刷新中' : '刷新仪表盘'"
            :aria-label="isDashboardRefreshing ? '刷新中' : '刷新仪表盘'"
            @click="refreshDashboard"
          >
            <AppIcon v-if="!isDashboardRefreshing" name="refresh" :size="18" />
          </el-button>
          <el-dropdown class="workspace-user-dropdown-shell" trigger="click" @command="handleUserCommand">
            <el-button class="workspace-avatar-button" text aria-haspopup="menu" aria-label="账户菜单">
              <UserAvatar
                class="workspace-avatar"
                :src="currentUserAvatar"
                :username="currentUser?.username"
                :display-name="currentUserDisplayName"
                :first-name="currentUser?.first_name"
                size="sm"
              />
            </el-button>
            <template #dropdown>
              <div class="workspace-user-dropdown-panel">
                <div class="workspace-user-card">
                  <UserAvatar
                    class="workspace-avatar"
                    :src="currentUserAvatar"
                    :username="currentUser?.username"
                    :display-name="currentUserDisplayName"
                    :first-name="currentUser?.first_name"
                    size="md"
                  />
                  <div>
                    <strong>{{ currentUserDisplayName }}</strong>
                    <span>{{ currentUserAccount }}</span>
                  </div>
                </div>
                <el-dropdown-menu class="workspace-user-dropdown-menu">
                  <el-dropdown-item command="profile" :disabled="!canAccessPage('profile')">
                    <AppIcon name="user" :size="16" />
                    <span>个人中心</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="lock">
                    <AppIcon name="lock" :size="16" />
                    <span>锁定屏幕</span>
                  </el-dropdown-item>
                  <el-dropdown-item command="logout" divided class="workspace-menu-logout">
                    <AppIcon name="logout" :size="16" />
                    <span>退出登录</span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </div>
            </template>
          </el-dropdown>
        </div>
      </header>

      <section class="workspace-body">
        <template v-if="!isLocked || hasWorkspaceDataLoaded">
          <Transition name="fade-transform" mode="out-in" appear>
            <div :key="activeTool" class="workspace-tool-view">
              <DashboardPage v-if="activeTool === 'dashboard'" ref="dashboardPageRef" />
              <IpScanner v-else-if="activeTool === 'ip'" />
              <HostManager v-else-if="activeTool === 'hosts'" />
              <SessionAuditManager v-else-if="activeTool === 'sessionAudits'" />
              <BulkExecutionPanel v-else-if="activeTool === 'bulkExecution'" />
              <ApplicationMarketPanel v-else-if="activeTool === 'applicationMarket'" />
              <AccountManager v-else-if="activeTool === 'accounts'" />
              <DeviceManager v-else-if="activeTool === 'companyDevices'" />
              <MachineProbe v-else-if="activeTool === 'ports'" />
              <SubnetCalculator v-else-if="activeTool === 'subnet'" />
              <AuthenticatorPanel v-else-if="activeTool === 'auth'" />
              <PasswordGenerator v-else-if="activeTool === 'password'" />
              <SecurityScanPanel v-else-if="activeTool === 'securityScan'" />
              <LoginLogManager v-else-if="activeTool === 'loginLogs'" />
              <OperationLogManager v-else-if="activeTool === 'operationLogs'" />
              <UserManager v-else-if="activeTool === 'users'" />
              <RoleManager v-else-if="activeTool === 'roles'" />
              <ProfileCenter v-else-if="activeTool === 'profile'" />
              <SystemSettingsPanel v-else-if="activeTool === 'systemSettings'" />
            </div>
          </Transition>
        </template>
      </section>
      <footer v-if="layoutFooter.enabled" class="workspace-footer" :style="footerStyle">
        <span>{{ footerText }}</span>
        <a
          v-if="layoutFooter.linkText && layoutFooter.linkUrl"
          :href="layoutFooter.linkUrl"
          :target="isExternalFooterLink ? '_blank' : undefined"
          :rel="isExternalFooterLink ? 'noreferrer' : undefined"
        >
          {{ footerLinkText }}
        </a>
      </footer>
    </section>

    <div class="workspace-float-actions" role="group" aria-label="快捷操作">
      <el-tooltip :content="isWorkspaceDark ? '切换明亮模式' : '切换暗黑模式'" placement="left">
        <el-button class="workspace-float-action" circle @click="handleFloatAction('theme')">
          <AppIcon :name="isWorkspaceDark ? 'sun' : 'moon'" :size="18" />
        </el-button>
      </el-tooltip>
      <el-tooltip v-if="activeTool === 'dashboard'" content="刷新仪表盘" placement="left">
        <el-button class="workspace-float-action" circle :loading="isDashboardRefreshing" @click="handleFloatAction('refresh')">
          <AppIcon v-if="!isDashboardRefreshing" name="refresh" :size="18" />
        </el-button>
      </el-tooltip>
      <el-tooltip content="回到顶部" placement="left">
        <el-button class="workspace-float-action" circle @click="handleFloatAction('top')">
          <AppIcon class="workspace-float-top-icon" name="chevronDown" :size="18" />
        </el-button>
      </el-tooltip>
    </div>

    <WatermarkOverlay v-if="shouldShowWatermark" :text="watermarkText" />
    <LockScreenOverlay
      v-if="currentUser"
      :locked="isLocked"
      :avatar-url="currentUserAvatar"
      :username="currentUser.username"
      :display-name="currentUserDisplayName"
      :first-name="currentUser.first_name"
      :account="currentUserAccount"
      :unlock-session="unlockSession"
      :logout="logout"
    />

    <HostExportDialog
      v-if="hostTransferDialog === 'export'"
      v-model:scope="hostExportScope"
      v-model:format="hostTransferFormat"
      :columns="hostExportColumnOptions"
      :selected-columns="selectedHostExportColumns"
      :all-columns-selected="allHostExportColumnsSelected"
      :selected-count="selectedManagedHostCount"
      @close="closeHostTransferDialog"
      @confirm="confirmHostExport"
      @toggle-column="toggleHostExportColumn"
      @toggle-all-columns="toggleAllHostExportColumns"
    />
    <HostImportDialog
      v-else-if="hostTransferDialog === 'import'"
      @close="closeHostTransferDialog"
      @confirm="confirmHostTransfer"
      @download-template="downloadHostImportTemplate"
    />

    <el-dialog :model-value="Boolean(qrPreview)" class="qr-modal share-modal" title="分享二维码" width="420px" :close-on-click-modal="false" @close="qrPreview = null">
      <template v-if="qrPreview" #default>
        <div class="popup-body qr-modal-body">
          <h2>分享二维码</h2>
          <p>扫码后可直接导入 {{ qrPreview.issuer }} 的双因子配置。</p>
          <div class="qr-frame">
            <img :src="qrPreview.dataUrl" alt="TOTP 二维码" />
          </div>
          <div class="qr-meta">
            <strong>{{ qrPreview.issuer }}</strong>
            <span>{{ qrPreview.account }}</span>
          </div>
        </div>
      </template>
      <template #footer>
        <div class="qr-actions popup-actions">
          <el-button :disabled="!qrPreview" @click="qrPreview && copyText(qrPreview.uri, '已复制分享链接。')">复制分享链接</el-button>
          <el-button type="primary" @click="qrPreview = null">完成</el-button>
        </div>
      </template>
    </el-dialog>
  </main>
</template>
