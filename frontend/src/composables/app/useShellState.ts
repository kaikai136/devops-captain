import { computed, ref, watch } from 'vue';

import type { SidebarIconName } from '@shared/components/SidebarIcon.vue';
import { dashboardNavItem, navGroups } from '@app/navigation';
import { navGroupIcons, navItemIcons } from '@app/sidebarIcons';
import type { ToolKey } from '../../types';

type WorkspaceTheme = 'light' | 'dark';

const WORKSPACE_THEME_STORAGE_KEY = 'ops-tool.workspace-theme';
const ACTIVE_TOOL_STORAGE_KEY = 'ops-tool.active-tool';

export function useShellState() {
  const activeTool = ref<ToolKey>(readActiveTool());
  const groupsOpen = ref({ network: true, host: true, market: true, company: true, security: true, system: true });
  const sidebarCollapsed = ref(false);
  const hoveredNavGroup = ref<string | null>(null);
  const workspaceTheme = ref<WorkspaceTheme>(readWorkspaceTheme());
  let navFlyoutTimer: number | undefined;

  const activeNavGroup = computed(() => navGroups.find((group) => group.items.some((item) => item.key === activeTool.value)) ?? navGroups[0]);
  const activeNavItem = computed(() => activeNavGroup.value.items.find((item) => item.key === activeTool.value) ?? activeNavGroup.value.items[0]);
  const isWorkspaceDark = computed(() => workspaceTheme.value === 'dark');

  function setActiveTool(key: ToolKey) {
    activeTool.value = key;
  }

  watch(activeTool, (key) => {
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(ACTIVE_TOOL_STORAGE_KEY, key);
    }
  });

  function selectNavItem(key: ToolKey) {
    setActiveTool(key);
    closeNavFlyout(80);
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value;
  }

  function toggleWorkspaceTheme() {
    workspaceTheme.value = isWorkspaceDark.value ? 'light' : 'dark';
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(WORKSPACE_THEME_STORAGE_KEY, workspaceTheme.value);
    }
  }

  function openNavFlyout(key: string) {
    window.clearTimeout(navFlyoutTimer);
    hoveredNavGroup.value = key;
  }

  function closeNavFlyout(delay = 220) {
    window.clearTimeout(navFlyoutTimer);
    navFlyoutTimer = window.setTimeout(() => {
      hoveredNavGroup.value = null;
    }, delay);
  }

  function cleanupShellState() {
    window.clearTimeout(navFlyoutTimer);
  }

  return {
    activeTool,
    groupsOpen,
    sidebarCollapsed,
    hoveredNavGroup,
    workspaceTheme,
    isWorkspaceDark,
    navGroups,
    dashboardNavItem,
    activeNavGroup,
    activeNavItem,
    setActiveTool,
    selectNavItem,
    toggleSidebar,
    toggleWorkspaceTheme,
    openNavFlyout,
    closeNavFlyout,
    navItemIcon,
    navGroupIcon,
    cleanupShellState,
  };
}

function navItemIcon(key: ToolKey): SidebarIconName {
  return navItemIcons[key];
}

function navGroupIcon(key: string): SidebarIconName {
  return navGroupIcons[key as keyof typeof navGroupIcons] ?? 'dashboard';
}

function readWorkspaceTheme(): WorkspaceTheme {
  if (typeof window === 'undefined') return 'light';
  return window.localStorage.getItem(WORKSPACE_THEME_STORAGE_KEY) === 'dark' ? 'dark' : 'light';
}

function readActiveTool(): ToolKey {
  if (typeof window === 'undefined') return 'dashboard';
  const stored = window.localStorage.getItem(ACTIVE_TOOL_STORAGE_KEY);
  return isToolKey(stored) ? stored : 'dashboard';
}

function isToolKey(value: string | null): value is ToolKey {
  if (!value) return false;
  if (value === dashboardNavItem.key) return true;
  return navGroups.some((group) => group.items.some((item) => item.key === value));
}
