import { computed, nextTick, ref, watch } from 'vue';

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
  let themeTransitionActive = false;

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

  async function toggleWorkspaceTheme(event?: MouseEvent) {
    if (themeTransitionActive) return;
    let updated = false;
    const updateTheme = () => {
      if (updated) return;
      updated = true;
      workspaceTheme.value = isWorkspaceDark.value ? 'light' : 'dark';
      if (typeof window !== 'undefined') window.localStorage.setItem(WORKSPACE_THEME_STORAGE_KEY, workspaceTheme.value);
    };
    const browserDocument = typeof document === 'undefined' ? null : document as Document & {
      startViewTransition?: (update: () => Promise<void>) => { ready: Promise<void>; finished: Promise<void> };
    };
    if (!browserDocument?.startViewTransition || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      updateTheme();
      return;
    }
    const button = event?.currentTarget as HTMLElement | null;
    const bounds = button?.getBoundingClientRect();
    const horizontal = event && event.detail > 0 ? event.clientX : bounds ? bounds.left + bounds.width / 2 : window.innerWidth / 2;
    const vertical = event && event.detail > 0 ? event.clientY : bounds ? bounds.top + bounds.height / 2 : window.innerHeight / 2;
    const radius = Math.hypot(Math.max(horizontal, window.innerWidth - horizontal), Math.max(vertical, window.innerHeight - vertical));
    themeTransitionActive = true;
    browserDocument.documentElement.classList.add('workspace-theme-transition');
    try {
      const transition = browserDocument.startViewTransition(async () => { updateTheme(); await nextTick(); });
      void transition.finished.catch(() => {});
      await transition.ready;
      await browserDocument.documentElement.animate(
        { clipPath: [`circle(0px at ${horizontal}px ${vertical}px)`, `circle(${radius}px at ${horizontal}px ${vertical}px)`] },
        { duration: 680, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', pseudoElement: '::view-transition-new(root)' },
      ).finished;
      await transition.finished;
    } catch {
      updateTheme();
    } finally {
      browserDocument.documentElement.classList.remove('workspace-theme-transition');
      themeTransitionActive = false;
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
