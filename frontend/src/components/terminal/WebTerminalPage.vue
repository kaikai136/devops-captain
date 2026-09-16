<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { InputInstance } from 'element-plus';
import Guacamole from 'guacamole-common-js';
import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon, type ISearchOptions } from '@xterm/addon-search';
import { Terminal } from '@xterm/xterm';
import type { IBufferLine, IDisposable } from '@xterm/xterm';
import '@xterm/xterm/css/xterm.css';

import { ApiUnauthorizedError } from '../../api';
import { useSshTerminal } from '../../features/terminal/composables/useSshTerminal';
import { useTerminalResize } from '../../features/terminal/composables/useTerminalResize';
import { useTerminalTabs } from '../../features/terminal/composables/useTerminalTabs';
import SftpPanel from '../../features/terminal/components/files/SftpPanel.vue';
import {
  createTerminalQuickCommand,
  getTerminalMonitor,
  listTerminalQuickCommands,
  listTerminalTree,
  removeTerminalQuickCommand,
  reorderTerminalQuickCommands,
  updateTerminalQuickCommand,
} from '../../features/terminal/api/terminal';
import type {
  TerminalGroup,
  TerminalHost,
  TerminalMonitorResponse,
  TerminalQuickCommand,
  TerminalStatus,
  TerminalTabKind,
} from '../../features/terminal/types';
import {
  calculateRdpDisplayScale,
  buildRdpConnectionQuery as buildRdpConnectionQueryValue,
  buildRdpWebSocketUrl as buildRdpWebSocketUrlValue,
  buildTerminalWebSocketUrl,
  formatRdpConnectionErrorMessage,
  parseTerminalHostQuery,
} from '../../features/terminal/utils/protocol';
import {
  attachTerminalPasteHandler,
  getClipboardTextFromPasteEvent,
  normalizeTerminalPasteText,
  writeTextToClipboard,
} from '../../features/terminal/utils/terminalScreen';
import { AUTH_LOGOUT_EVENT_KEY } from '../../composables/app/useAuthSession';
import { getCurrentUser } from '../../services/auth';
import { getSystemSettingOrNull } from '../../services/system';
import {
  TERMINAL_FONT_SIZE_DEFAULT,
  TERMINAL_FONT_SIZE_MAX,
  TERMINAL_FONT_SIZE_MIN,
  clampTerminalFontSize,
  createDefaultTerminalSettings,
  normalizeTerminalSettings,
  readStoredTerminalFontSize,
} from '../../utils/terminalSettings';
import AppIcon from '@shared/components/AppIcon.vue';
import AppContextMenu from '@shared/components/context-menu/AppContextMenu.vue';
import type { ContextMenuEntry as TerminalContextMenuItem } from '@shared/components/context-menu/types';
import type { IconName } from '@shared/components/AppIcon.vue';
import type { AccountUser, TerminalSettingsConfig } from '../../types';

type GuacamoleClientInstance = InstanceType<typeof Guacamole.Client>;
type GuacamoleWebSocketTunnelInstance = InstanceType<typeof Guacamole.WebSocketTunnel>;
type GuacamoleMouseInstance = InstanceType<typeof Guacamole.Mouse>;
type GuacamoleKeyboardInstance = InstanceType<typeof Guacamole.Keyboard>;
type TerminalSidebarMode = 'hosts' | 'files' | 'commands';
type TerminalSplitMode = 'single' | 'auto' | 'horizontal' | 'vertical';
type TerminalTabColorId =
  | 'red'
  | 'orange'
  | 'amber'
  | 'yellow'
  | 'green'
  | 'emerald'
  | 'cyan'
  | 'sky'
  | 'blue'
  | 'violet'
  | 'pink'
  | 'rose';

interface TerminalTab {
  id: string;
  kind: TerminalTabKind;
  host: TerminalHost;
  customTitle: string;
  colorId: TerminalTabColorId | null;
  status: TerminalStatus;
  terminal: Terminal;
  fitAddon: FitAddon;
  searchAddon: SearchAddon;
  socket: WebSocket | null;
  guacClient: GuacamoleClientInstance | null;
  guacTunnel: GuacamoleWebSocketTunnelInstance | null;
  guacMouse: GuacamoleMouseInstance | null;
  guacKeyboard: GuacamoleKeyboardInstance | null;
  guacDisplayElement: HTMLElement | null;
  rdpErrorMessage: string;
  sessionId: string | null;
  mounted: boolean;
  disposables: IDisposable[];
  highlightState: TerminalHighlightState;
  suppressInterruptUntil: number;
  hasUnreadOutput: boolean;
  currentCwd: string;
  reconnectHintShown: boolean;
}

type TreeRow =
  | { kind: 'root'; group: TerminalRoot; level: number }
  | { kind: 'group'; group: TerminalGroup; level: number }
  | { kind: 'host'; host: TerminalHost; level: number };

interface TerminalRoot {
  id: null;
  name: string;
  count: number;
}

interface TerminalMessage {
  type: 'ready' | 'output' | 'cwd' | 'error' | 'closed' | 'pong';
  sessionId?: string;
  terminalSettings?: Partial<TerminalSettingsConfig>;
  data?: string;
  path?: string;
  message?: string;
  reason?: string;
}

interface TerminalHighlightRule {
  name: string;
  pattern: RegExp;
  open: string;
  close: string;
}

interface TerminalHighlightState {
  sgrActive: boolean;
  pendingControl: string;
}

interface TerminalSearchMatch {
  row: number;
  col: number;
  size: number;
}

interface PersistedTerminalTab {
  id: string;
  hostId: number;
  title?: string;
  colorId?: TerminalTabColorId;
}

interface PersistedTerminalWorkspace {
  tabs: PersistedTerminalTab[];
  activeTabId: string | null;
}


interface TerminalQuickCommandDraft {
  name: string;
  category: string;
  command: string;
  description: string;
  enabled: boolean;
  sortOrder: number;
}

interface TerminalQuickCommandDialogState {
  visible: boolean;
  mode: 'create' | 'edit';
  commandId: number | null;
  draft: TerminalQuickCommandDraft;
  saving: boolean;
  error: string;
}


interface TerminalContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  tabId: string | null;
  selectedText: string;
}


interface TerminalTabContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  tabId: string | null;
}

interface TerminalPastePromptState {
  visible: boolean;
  x: number;
  y: number;
  tabId: string | null;
  value: string;
}

interface TerminalTabColorOption {
  id: TerminalTabColorId;
  label: string;
  swatch: string;
  background: string;
  color: string;
  border: string;
  activeBackground: string;
  activeColor: string;
  activeBorder: string;
}

interface TerminalSplitModeOption {
  mode: TerminalSplitMode;
  label: string;
  icon: IconName;
}

const ANSI_CONTROL_PATTERN = /\x1b\][^\x07]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]/g;
const ANSI_CONTROL_PREFIX_PATTERN = /^\x1b(?:\[[0-?]*[ -/]*)?$/;
const CONTROL_C = '\x03';
const MOUSE_SELECTION_INTERRUPT_SUPPRESSION_MS = 250;
const MOUSE_DOUBLE_CLICK_INTERRUPT_SUPPRESSION_MS = 1200;
const MAX_CONNECTING_TERMINALS = 2;
const TERMINAL_WORKSPACE_STORAGE_KEY = 'ops-tool.web-terminal.workspace';
const TERMINAL_SIDEBAR_WIDTH_STORAGE_KEY = 'ops-tool.web-terminal.sidebar-width';
const TERMINAL_SIDEBAR_COLLAPSED_STORAGE_KEY = 'ops-tool.web-terminal.sidebar-collapsed';
const TERMINAL_FONT_SIZE_STORAGE_KEY = 'ops-tool.web-terminal.font-size';
const TERMINAL_SETTINGS_SETTING_KEY = 'terminal_settings';
const TERMINAL_SPLIT_MODE_STORAGE_KEY = 'ops-tool.web-terminal.split-mode';
const TERMINAL_SIDEBAR_DEFAULT_WIDTH = 284;
const TERMINAL_SIDEBAR_MIN_WIDTH = 200;
const TERMINAL_WORKSPACE_MIN_WIDTH = 360;
const TERMINAL_TAB_TITLE_MAX_LENGTH = 40;
const TERMINAL_MONITOR_REFRESH_MS = 5000;
const TERMINAL_QUICK_COMMAND_PANEL_HEIGHT_STORAGE_KEY = 'ops-tool.web-terminal.quick-command-panel-height';
const TERMINAL_QUICK_COMMAND_PANEL_COLLAPSED_STORAGE_KEY = 'ops-tool.web-terminal.quick-command-panel-collapsed';
const TERMINAL_QUICK_COMMAND_PANEL_DEFAULT_HEIGHT = 260;
const TERMINAL_QUICK_COMMAND_PANEL_MIN_HEIGHT = 160;
const TERMINAL_QUICK_COMMAND_PANEL_MAX_HEIGHT = 420;
const TERMINAL_SEARCH_DECORATIONS: NonNullable<ISearchOptions['decorations']> = {
  matchBackground: '#7c3aed',
  matchBorder: '#c084fc',
  matchOverviewRuler: '#a855f7',
  activeMatchBackground: '#a21caf',
  activeMatchBorder: '#f0abfc',
  activeMatchColorOverviewRuler: '#d946ef',
};
const terminalTabColorOptions: TerminalTabColorOption[] = [
  {
    id: 'red',
    label: '红色',
    swatch: '#ef4444',
    background: '#fff1f2',
    color: '#991b1b',
    border: '#f87171',
    activeBackground: '#dc2626',
    activeColor: '#ffffff',
    activeBorder: '#ef4444',
  },
  {
    id: 'orange',
    label: '橙色',
    swatch: '#f97316',
    background: '#fff7ed',
    color: '#9a3412',
    border: '#fb923c',
    activeBackground: '#ea580c',
    activeColor: '#ffffff',
    activeBorder: '#f97316',
  },
  {
    id: 'amber',
    label: '琥珀',
    swatch: '#f59e0b',
    background: '#fffbeb',
    color: '#92400e',
    border: '#fbbf24',
    activeBackground: '#d97706',
    activeColor: '#ffffff',
    activeBorder: '#f59e0b',
  },
  {
    id: 'yellow',
    label: '黄色',
    swatch: '#eab308',
    background: '#fefce8',
    color: '#854d0e',
    border: '#facc15',
    activeBackground: '#ca8a04',
    activeColor: '#ffffff',
    activeBorder: '#eab308',
  },
  {
    id: 'green',
    label: '绿色',
    swatch: '#22c55e',
    background: '#f0fdf4',
    color: '#166534',
    border: '#4ade80',
    activeBackground: '#16a34a',
    activeColor: '#ffffff',
    activeBorder: '#22c55e',
  },
  {
    id: 'emerald',
    label: '翡翠',
    swatch: '#10b981',
    background: '#ecfdf5',
    color: '#065f46',
    border: '#34d399',
    activeBackground: '#059669',
    activeColor: '#ffffff',
    activeBorder: '#10b981',
  },
  {
    id: 'cyan',
    label: '青色',
    swatch: '#06b6d4',
    background: '#ecfeff',
    color: '#155e75',
    border: '#22d3ee',
    activeBackground: '#0891b2',
    activeColor: '#ffffff',
    activeBorder: '#06b6d4',
  },
  {
    id: 'sky',
    label: '天蓝',
    swatch: '#0ea5e9',
    background: '#f0f9ff',
    color: '#075985',
    border: '#38bdf8',
    activeBackground: '#0284c7',
    activeColor: '#ffffff',
    activeBorder: '#0ea5e9',
  },
  {
    id: 'blue',
    label: '蓝色',
    swatch: '#3b82f6',
    background: '#eff6ff',
    color: '#1e40af',
    border: '#60a5fa',
    activeBackground: '#2563eb',
    activeColor: '#ffffff',
    activeBorder: '#3b82f6',
  },
  {
    id: 'violet',
    label: '紫色',
    swatch: '#8b5cf6',
    background: '#f5f3ff',
    color: '#5b21b6',
    border: '#a78bfa',
    activeBackground: '#7c3aed',
    activeColor: '#ffffff',
    activeBorder: '#8b5cf6',
  },
  {
    id: 'pink',
    label: '粉色',
    swatch: '#ec4899',
    background: '#fdf2f8',
    color: '#9d174d',
    border: '#f472b6',
    activeBackground: '#db2777',
    activeColor: '#ffffff',
    activeBorder: '#ec4899',
  },
  {
    id: 'rose',
    label: '玫红',
    swatch: '#f43f5e',
    background: '#fff1f2',
    color: '#9f1239',
    border: '#fb7185',
    activeBackground: '#e11d48',
    activeColor: '#ffffff',
    activeBorder: '#f43f5e',
  },
];
const terminalTabColorOptionMap = new Map<TerminalTabColorId, TerminalTabColorOption>(
  terminalTabColorOptions.map((option) => [option.id, option]),
);
const terminalHighlightRules: TerminalHighlightRule[] = [
  {
    name: 'danger',
    pattern: /\b(error|failed|failure|exception|traceback|denied|refused|fatal|critical)\b/gi,
    open: '\x1b[48;5;52m',
    close: '\x1b[49m',
  },
  {
    name: 'warning',
    pattern: /\b(warn|warning|timeout|retry|deprecated|unreachable)\b/gi,
    open: '\x1b[48;5;58m',
    close: '\x1b[49m',
  },
  {
    name: 'success',
    pattern: /\b(success|succeeded|ok|done|completed|running|started|active)\b/gi,
    open: '\x1b[48;5;22m',
    close: '\x1b[49m',
  },
  {
    name: 'ip',
    pattern: /\b(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}\b/g,
    open: '\x1b[48;5;24m',
    close: '\x1b[49m',
  },
];
const terminalSplitModeOptions: TerminalSplitModeOption[] = [
  { mode: 'single', label: '单屏模式', icon: 'maximize' },
  { mode: 'auto', label: '自动平铺所有会话', icon: 'dashboard' },
  { mode: 'horizontal', label: '水平平铺', icon: 'rows' },
  { mode: 'vertical', label: '垂直平铺', icon: 'panelLeft' },
];
const terminalContextMenu = ref<TerminalContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  tabId: null,
  selectedText: '',
});
const terminalTabContextMenu = ref<TerminalTabContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  tabId: null,
});
const terminalPastePrompt = ref<TerminalPastePromptState>({
  visible: false,
  x: 0,
  y: 0,
  tabId: null,
  value: '',
});
const terminalMonitorData = ref<TerminalMonitorResponse | null>(null);
const isTerminalMonitorLoading = ref(false);
const terminalMonitorError = ref('');
const isTerminalMonitorPanelOpen = ref(false);
let terminalMonitorRequestId = 0;
let terminalMonitorTimer: ReturnType<typeof window.setInterval> | null = null;
const terminalQuickCommands = ref<TerminalQuickCommand[]>([]);
const terminalQuickCommandCategory = ref('all');
const terminalQuickCommandSearch = ref('');
const isTerminalQuickCommandLoading = ref(false);
const terminalQuickCommandError = ref('');
const terminalQuickCommandPanelHeight = ref(readTerminalQuickCommandPanelHeight());
const isTerminalQuickCommandPanelCollapsed = ref(readTerminalQuickCommandPanelCollapsed());
const isTerminalQuickCommandPanelResizing = ref(false);
const terminalQuickCommandDialog = ref<TerminalQuickCommandDialogState>({
  visible: false,
  mode: 'create',
  commandId: null,
  draft: createTerminalQuickCommandDraft(),
  saving: false,
  error: '',
});
const terminalCurrentUser = ref<AccountUser | null>(null);
let terminalQuickCommandResizeStartY = 0;
let terminalQuickCommandResizeStartHeight = TERMINAL_QUICK_COMMAND_PANEL_DEFAULT_HEIGHT;

const groups = ref<TerminalGroup[]>([]);
const collapsed = ref<Set<number>>(new Set());
const rootExpanded = ref(true);
const rootLabel = ref(readTerminalRootLabel());
const search = ref('');
const {
  tabs,
  activeTabId,
  activeTab,
  openTab: addTerminalTab,
  activateTab: selectTerminalTab,
  replaceTabs: replaceTerminalTabs,
  closeTabs: removeTerminalTabs,
} = useTerminalTabs<TerminalTab>({ disposeTab });
const isTerminalTabMenuOpen = ref(false);
const isTerminalSplitMenuOpen = ref(false);
const isTerminalMultiExecutionEnabled = ref(false);
const multiExecutionExcludedTabIds = ref<Set<string>>(new Set());
const isTerminalSearchOpen = ref(false);
const terminalSearchQuery = ref('');
const terminalSearchResultIndex = ref(-1);
const terminalSearchResultCount = ref(0);
const terminalSearchInputRef = ref<InputInstance | null>(null);
const terminalPasteInputRef = ref<InputInstance | null>(null);
const terminalTabsRef = ref<HTMLElement | null>(null);
const canScrollTerminalTabsLeft = ref(false);
const canScrollTerminalTabsRight = ref(false);
const isLoadingTree = ref(false);
const treeError = ref('');
const highlightEnabled = ref(false);
const terminalSettings = ref<TerminalSettingsConfig>(createDefaultTerminalSettings());
const terminalFontSize = ref(readTerminalFontSize());
const terminalSplitMode = ref<TerminalSplitMode>(readTerminalSplitMode());
const terminalSidebarMode = ref<TerminalSidebarMode>('hosts');
const sidebarWidth = ref(readTerminalSidebarWidth());
const isTerminalSidebarCollapsed = ref(readTerminalSidebarCollapsed());
const isResizingSidebar = ref(false);
let sidebarResizeStartX = 0;
let sidebarResizeStartWidth = TERMINAL_SIDEBAR_DEFAULT_WIDTH;
const terminalContainers = new Map<string, HTMLElement>();
const terminalHeartbeatTimers = new Map<string, number>();
const pendingConnectTabIds: string[] = [];
const connectingTabIds = new Set<string>();
let terminalAuthRedirecting = false;

const rows = computed(() => {
  const query = search.value.trim().toLowerCase();
  const root: TreeRow = { kind: 'root', group: terminalRoot.value, level: 0 };
  const treeRows = rootExpanded.value ? [root, ...flattenTerminalRows(groups.value, collapsed.value, 1)] : [root];
  return treeRows.filter((row) => {
    if (!query) return true;
    if (row.kind === 'root') return row.group.name.toLowerCase().includes(query);
    if (row.kind === 'group') return row.group.name.toLowerCase().includes(query);
    return [row.host.name, row.host.privateIp, row.host.publicIp, row.host.loginUser]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
});

const connectedTerminalTabs = computed(() => tabs.value.filter((tab) => tab.status === 'connected'));
const isTerminalSplitActive = computed(
  () => terminalSplitMode.value !== 'single' && connectedTerminalTabs.value.length >= 2 && activeTab.value?.status === 'connected',
);
const visibleTerminalTabs = computed(() => (isTerminalSplitActive.value ? connectedTerminalTabs.value : activeTab.value ? [activeTab.value] : []));
const terminalSplitModeLabel = computed(
  () => terminalSplitModeOptions.find((option) => option.mode === terminalSplitMode.value)?.label ?? '单屏模式',
);
const terminalScreenStyle = computed<Record<string, string>>(() => {
  if (!isTerminalSplitActive.value) return {} as Record<string, string>;
  const count = visibleTerminalTabs.value.length;
  const columns =
    terminalSplitMode.value === 'horizontal'
      ? 1
      : terminalSplitMode.value === 'vertical'
        ? count
        : Math.ceil(Math.sqrt(count));
  const rows = terminalSplitMode.value === 'vertical' ? 1 : Math.ceil(count / columns);
  return {
    '--terminal-split-columns': String(columns),
    '--terminal-split-rows': String(rows),
  };
});
const activeTerminalNodeName = computed(() => activeTab.value?.host.name ?? '未选择主机');
const terminalSidebarToggleLabel = computed(() => (isTerminalSidebarCollapsed.value ? '展开侧栏' : '收起侧栏'));
const terminalMonitorNodeName = computed(() => activeTab.value?.host.name ?? '??????');
const terminalQuickCommandCategories = computed(() => {
  const categories = terminalQuickCommands.value.map((command) => command.category).filter(Boolean);
  return [...new Set(categories)].sort((left, right) => left.localeCompare(right, 'zh-Hans-CN'));
});
const filteredTerminalQuickCommands = computed(() => {
  const query = terminalQuickCommandSearch.value.trim().toLowerCase();
  return terminalQuickCommands.value.filter((command) => {
    const matchesCategory = terminalQuickCommandCategory.value === 'all' || command.category === terminalQuickCommandCategory.value;
    if (!matchesCategory) return false;
    if (!query) return true;
    return [command.name, command.category, command.command, command.description]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(query));
  });
});
const activeTerminalSupportsSshTools = computed(() => Boolean(activeTab.value && activeTab.value.kind === 'ssh'));
const activeTerminalReady = computed(
  () => activeTab.value?.kind === 'ssh' && activeTab.value.status === 'connected' && activeTab.value.socket?.readyState === WebSocket.OPEN,
);
const terminalSearchResultText = computed(() => {
  if (!terminalSearchQuery.value.trim()) return '';
  if (terminalSearchResultCount.value <= 0) return '0';
  if (terminalSearchResultIndex.value < 0) return String(terminalSearchResultCount.value);
  return `${terminalSearchResultIndex.value + 1}/${terminalSearchResultCount.value}`;
});
const terminalMultiExecutionTargets = computed(() =>
  tabs.value.filter((tab) => isTerminalTabReady(tab) && !multiExecutionExcludedTabIds.value.has(tab.id)),
);
const terminalMultiExecutionTargetCount = computed(() => terminalMultiExecutionTargets.value.length);
const hasTerminalMultiExecutionCandidates = computed(() => tabs.value.some((tab) => isTerminalTabReady(tab)));
const canSendToTerminalMultiExecutionTargets = computed(
  () => isTerminalMultiExecutionEnabled.value && terminalMultiExecutionTargetCount.value > 0,
);
const terminalQuickCommandReady = computed(() =>
  isTerminalMultiExecutionEnabled.value ? canSendToTerminalMultiExecutionTargets.value : activeTerminalReady.value,
);
const canDecreaseTerminalFontSize = computed(() => terminalFontSize.value > TERMINAL_FONT_SIZE_MIN);
const canIncreaseTerminalFontSize = computed(() => terminalFontSize.value < TERMINAL_FONT_SIZE_MAX);
const canUseTerminalQuickCommands = computed(() => {
  const user = terminalCurrentUser.value;
  if (!user) return false;
  if (user.is_superuser || user.is_staff) return true;
  return (user.featurePermissionCodes ?? []).includes('action_hosts_quick_commands');
});
const shouldShowTerminalQuickCommandPanel = computed(
  () => activeTerminalSupportsSshTools.value && canUseTerminalQuickCommands.value && terminalQuickCommands.value.length > 0,
);
const terminalQuickCommandPanelStyle = computed<Record<string, string>>(() => ({
  '--terminal-quick-command-height':
    !shouldShowTerminalQuickCommandPanel.value || isTerminalQuickCommandPanelCollapsed.value ? '0px' : `${terminalQuickCommandPanelHeight.value}px`,
}));
const terminalContextMenuItems = computed<TerminalContextMenuItem[]>(() => {
  const tab = getTerminalContextMenuTab();
  const selectedText = terminalContextMenu.value.selectedText.trim();
  const menuX = terminalContextMenu.value.x;
  const menuY = terminalContextMenu.value.y;
  const hasSelection = Boolean(selectedText);
  const isReady = Boolean(tab && isTerminalTabReady(tab));
  const items: TerminalContextMenuItem[] = [];

  if (hasSelection) {
    items.push(
      { id: 'copy-selection', label: '复制', icon: 'copy', enabled: true, shortcut: 'Ctrl+Shift+C', action: () => copyTerminalContextText(selectedText) },
      { id: 'find-selection', label: '查找选中内容', icon: 'search', enabled: true, shortcut: 'Ctrl+Shift+F', action: () => findTerminalText(selectedText) },
      {
        id: 'online-search',
        label: '在线搜索',
        icon: 'globe',
        enabled: true,
        action: () => undefined,
        children: [
          { id: 'search-selection', label: '搜索选中内容', icon: 'search', enabled: true, action: () => openTerminalOnlineSearch(selectedText) },
          { id: 'search-error', label: '搜索报错关键词', icon: 'alert', enabled: true, action: () => openTerminalOnlineSearch(`${selectedText} linux error`) },
          { id: 'search-command', label: '搜索命令用法', icon: 'terminal', enabled: true, action: () => openTerminalOnlineSearch(`${selectedText} linux command usage`) },
        ],
      },
      {
        id: 'ai',
        label: 'AI',
        icon: 'zap',
        enabled: true,
        action: () => undefined,
        children: [
          { id: 'ai-explain', label: '解释选中内容', icon: 'circleHelp', enabled: false, action: () => undefined },
          { id: 'ai-error', label: '分析错误原因', icon: 'alert', enabled: false, action: () => undefined },
          { id: 'ai-fix', label: '生成修复建议', icon: 'settings', enabled: false, action: () => undefined },
          { id: 'ai-summary', label: '总结这段输出', icon: 'file', enabled: false, action: () => undefined },
        ],
      },
      {
        id: 'translate',
        label: '翻译',
        icon: 'globe',
        enabled: true,
        action: () => undefined,
        children: [
          { id: 'translate-zh', label: '翻译为中文', icon: 'globe', enabled: true, action: () => openTerminalTranslation(selectedText, 'zh-Hans') },
          { id: 'translate-en', label: '翻译为英文', icon: 'globe', enabled: true, action: () => openTerminalTranslation(selectedText, 'en') },
        ],
      },
      { id: 'paste-selection', label: '粘贴选定文本到终端', icon: 'clipboard', enabled: isReady, separatorBefore: true, action: () => sendTextToTerminal(selectedText, tab) },
      { id: 'paste-selection-single-line', label: '粘贴为单行', icon: 'cornerDownLeft', enabled: isReady, action: () => sendTextToTerminal(toSingleLineTerminalText(selectedText), tab) },
      { id: 'save-selection-command', label: '保存为快捷命令...', icon: 'bookmark', enabled: canUseTerminalQuickCommands.value, action: () => openTerminalQuickCommandDialogFromText(selectedText) },
    );
  } else {
    items.push(
      { id: 'paste', label: '粘贴', icon: 'clipboard', enabled: isReady, shortcut: 'Ctrl+Shift+V', action: () => pasteClipboardToTerminal(tab, menuX, menuY) },
      { id: 'find', label: '查找...', icon: 'search', enabled: true, shortcut: 'Ctrl+Shift+F', action: () => promptFindTerminalText() },
      {
        id: 'quick-commands',
        label: '快捷命令',
        icon: 'zap',
        enabled: canUseTerminalQuickCommands.value,
        action: () => undefined,
        children: getTerminalQuickCommandContextItems(tab),
      },
    );
  }

  return [
    ...items,
    getTerminalSessionContextMenu(tab),
    getTerminalControlKeyContextMenu(tab),
    getTerminalViewContextMenu(tab),
    getTerminalBufferContextMenu(tab),
  ];
});

const terminalTabContextMenuItems = computed<TerminalContextMenuItem[]>(() => {
  const tab = getTerminalTabContextMenuTab();
  const hasTab = Boolean(tab);
  const serverIp = tab ? getTerminalServerIp(tab) : '';
  const rightSideTabs = tab ? getTerminalTabsRightOf(tab) : [];
  const hasInactiveTabs = Boolean(tab && tabs.value.some((item) => item.id !== tab.id));

  return [
    {
      id: 'tab-color',
      label: '设置标签页颜色',
      icon: 'palette',
      enabled: hasTab,
      action: () => undefined,
      children: [
        ...terminalTabColorOptions.map<TerminalContextMenuItem>((option) => ({
          id: `tab-color-${option.id}`,
          label: option.label,
          icon: 'palette',
          enabled: hasTab,
          selected: tab?.colorId === option.id,
          swatchColor: option.swatch,
          action: () => {
            if (tab) setTerminalTabColor(tab, option.id);
          },
        })),
        {
          id: 'tab-color-reset',
          label: '恢复默认颜色',
          icon: 'reset',
          enabled: Boolean(tab?.colorId),
          selected: Boolean(tab && !tab.colorId),
          separatorBefore: true,
          action: () => {
            if (tab) setTerminalTabColor(tab, null);
          },
        },
      ],
    },
    { id: 'tab-rename', label: '重命名标签名称', icon: 'edit', enabled: hasTab, action: () => { if (tab) renameTerminalTab(tab); } },
    { id: 'tab-copy-name', label: '复制标签名称', icon: 'copy', enabled: hasTab, action: async () => { if (tab) await copyTerminalContextText(getTerminalTabLabel(tab)); } },
    { id: 'tab-copy-ip', label: '复制服务器 IP', icon: 'copy', enabled: Boolean(serverIp), action: () => copyTerminalContextText(serverIp) },
    {
      id: 'tab-copy-session',
      label: '复制会话信息',
      icon: 'copy',
      enabled: hasTab,
      separatorBefore: true,
      action: async () => {
        if (tab) await copyTerminalContextText(getTerminalSessionInfo(tab));
      },
    },
    { id: 'tab-duplicate', label: '新建同主机标签', icon: 'plus', enabled: hasTab, action: async () => { if (tab) await openHostTab(tab.host); } },
    {
      id: 'tab-quick-commands',
      label: '快捷命令',
      icon: 'zap',
      enabled: canUseTerminalQuickCommands.value,
      action: () => undefined,
      children: getTerminalTabQuickCommandItems(tab),
    },
    {
      id: 'tab-reconnect',
      label: '重新连接',
      icon: 'refresh',
      enabled: Boolean(tab && (tab.status === 'closed' || tab.status === 'error')),
      separatorBefore: true,
      action: () => {
        if (tab) reconnectTerminalTab(tab);
      },
    },
    {
      id: 'tab-disconnect',
      label: '断开连接',
      icon: 'logout',
      enabled: canDisconnectTerminalTab(tab),
      danger: true,
      action: () => {
        if (tab) disconnectTerminalTab(tab);
      },
    },
    { id: 'tab-split-horizontal', label: '水平拆分会话', icon: 'rows', enabled: true, separatorBefore: true, action: () => setTerminalSplitMode('horizontal') },
    { id: 'tab-split-vertical', label: '垂直拆分会话', icon: 'panelLeft', enabled: true, action: () => setTerminalSplitMode('vertical') },
    { id: 'tab-split-single', label: '合并所有窗格', icon: 'maximize', enabled: terminalSplitMode.value !== 'single', action: () => setTerminalSplitMode('single') },
    {
      id: 'tab-close-current',
      label: '关闭当前',
      icon: 'x',
      enabled: hasTab,
      danger: true,
      separatorBefore: true,
      action: async () => {
        if (tab) await closeTab(tab);
      },
    },
    {
      id: 'tab-close-all',
      label: '关闭所有',
      icon: 'x',
      enabled: tabs.value.length > 0,
      danger: true,
      action: () => closeTerminalTabs(tabs.value),
    },
    {
      id: 'tab-close-inactive',
      label: '关闭非活动',
      icon: 'x',
      enabled: hasInactiveTabs,
      danger: true,
      action: async () => {
        if (tab) await closeTerminalTabs(tabs.value.filter((item) => item.id !== tab.id));
      },
    },
    {
      id: 'tab-close-right',
      label: '关闭右侧标签',
      icon: 'moveRight',
      enabled: rightSideTabs.length > 0,
      danger: true,
      action: () => closeTerminalTabs(rightSideTabs),
    },
  ];
});

const terminalRoot = computed<TerminalRoot>(() => ({
  id: null,
  name: rootLabel.value,
  count: countTerminalHosts(groups.value),
}));

const workspaceTitle = computed(() => {
  if (!activeTab.value) return '选择左侧主机开始连接';
  const tab = activeTab.value;
  const host = tab.host;
  return `${getTerminalTabLabel(tab)} / ${host.publicIp || host.privateIp}:${host.port}`;
});

function normalizeTerminalTabTitle(value: unknown) {
  if (typeof value !== 'string') return '';
  return value.trim().slice(0, TERMINAL_TAB_TITLE_MAX_LENGTH);
}

function isTerminalTabColorId(value: unknown): value is TerminalTabColorId {
  return typeof value === 'string' && terminalTabColorOptionMap.has(value as TerminalTabColorId);
}

function normalizeTerminalTabColorId(value: unknown): TerminalTabColorId | null {
  return isTerminalTabColorId(value) ? value : null;
}

function getTerminalTabLabel(tab: TerminalTab) {
  return tab.customTitle || tab.host.name;
}

function getTerminalHostTooltip(host: TerminalHost) {
  return host.privateIp || host.publicIp || host.name;
}

function getTerminalMultiExecutionStatusText() {
  const total = tabs.value.filter((tab) => isTerminalTabReady(tab)).length;
  const targetCount = terminalMultiExecutionTargetCount.value;
  if (!total) return '没有已连接终端';
  return `键入内容将发送到 ${targetCount} / ${total} 个已连接终端`;
}

function isTerminalMultiExecutionExcluded(tab: TerminalTab) {
  return multiExecutionExcludedTabIds.value.has(tab.id);
}

function shouldShowTerminalMultiExecutionTabIndicator(tab: TerminalTab) {
  return isTerminalMultiExecutionEnabled.value && isTerminalTabReady(tab) && !isTerminalMultiExecutionExcluded(tab);
}

function setTerminalMultiExecutionExcluded(tab: TerminalTab, excluded: boolean) {
  const next = new Set(multiExecutionExcludedTabIds.value);
  if (excluded) {
    next.add(tab.id);
  } else {
    next.delete(tab.id);
  }
  multiExecutionExcludedTabIds.value = next;
}

function checkedFromControl(value: Event | boolean | string | number) {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') return value === 'true';
  if (typeof value === 'number') return value !== 0;
  return (value.target as HTMLInputElement).checked;
}

function setTerminalMultiExecutionExcludedFromEvent(tab: TerminalTab, value: Event | boolean | string | number) {
  setTerminalMultiExecutionExcluded(tab, checkedFromControl(value));
}

function pruneTerminalMultiExecutionExclusions() {
  if (!multiExecutionExcludedTabIds.value.size) return;
  const knownTabIds = new Set(tabs.value.map((tab) => tab.id));
  const next = new Set([...multiExecutionExcludedTabIds.value].filter((tabId) => knownTabIds.has(tabId)));
  if (next.size !== multiExecutionExcludedTabIds.value.size) {
    multiExecutionExcludedTabIds.value = next;
  }
}

async function enableTerminalMultiExecution() {
  if (!hasTerminalMultiExecutionCandidates.value) return;
  const firstTarget = terminalMultiExecutionTargets.value[0];
  if (firstTarget && !isTerminalTabReady(activeTab.value)) {
    await activateTab(firstTarget.id);
  }
  isTerminalMultiExecutionEnabled.value = true;
  pruneTerminalMultiExecutionExclusions();
  if (terminalSplitMode.value === 'single' && connectedTerminalTabs.value.length >= 2) {
    setTerminalSplitMode('auto');
  } else {
    fitVisibleTerminalsSoon();
  }
}

function exitTerminalMultiExecution() {
  isTerminalMultiExecutionEnabled.value = false;
  multiExecutionExcludedTabIds.value = new Set();
  fitVisibleTerminalsSoon();
}

async function toggleTerminalMultiExecution() {
  if (isTerminalMultiExecutionEnabled.value) {
    exitTerminalMultiExecution();
  } else {
    await enableTerminalMultiExecution();
  }
}

function sendTerminalInput(tab: TerminalTab | null, data: string, options: { focus?: boolean } = {}) {
  if (!data || !isTerminalTabReady(tab)) return false;
  sshTerminal.send(tab, data);
  if (options.focus) tab.terminal.focus();
  return true;
}

function getTerminalMultiExecutionBroadcastTargets(sourceTab: TerminalTab | null = null) {
  if (!isTerminalMultiExecutionEnabled.value) return [];
  if (sourceTab && isTerminalMultiExecutionExcluded(sourceTab)) return [];
  return terminalMultiExecutionTargets.value.filter((tab) => tab.id !== sourceTab?.id);
}

function broadcastTerminalInputToMultiExecutionTargets(data: string, sourceTab: TerminalTab | null = null) {
  if (!data) return 0;
  const targets = sourceTab ? getTerminalMultiExecutionBroadcastTargets(sourceTab) : terminalMultiExecutionTargets.value;
  let sentCount = 0;
  for (const tab of targets) {
    if (sendTerminalInput(tab, data)) sentCount += 1;
  }
  return sentCount;
}

function sendTerminalInputToMultiExecutionTargets(data: string) {
  if (!data || !canSendToTerminalMultiExecutionTargets.value) return false;
  const sentCount = broadcastTerminalInputToMultiExecutionTargets(data);
  activeTab.value?.terminal.focus();
  return sentCount > 0;
}

async function pasteClipboardToTerminalMultiExecutionTargets() {
  if (!canSendToTerminalMultiExecutionTargets.value) return;
  try {
    const value = await navigator.clipboard?.readText();
    if (value) sendPastedTextToMultiExecutionTargets(value);
  } catch {
    // Keep the multi-paste action quiet when the browser blocks clipboard reads.
  }
}

function canSendQuickCommandToTab(tab: TerminalTab | null) {
  return isTerminalMultiExecutionEnabled.value ? canSendToTerminalMultiExecutionTargets.value : isTerminalTabReady(tab);
}

function getTerminalServerIp(tab: TerminalTab | null) {
  return tab?.host.publicIp || tab?.host.privateIp || '';
}

function getTerminalTabStyle(tab: TerminalTab): Record<string, string> {
  const option = tab.colorId ? terminalTabColorOptionMap.get(tab.colorId) : null;
  if (!option) return {};
  return {
    '--terminal-tab-bg': option.background,
    '--terminal-tab-color': option.color,
    '--terminal-tab-border': option.border,
    '--terminal-tab-hover-bg': option.background,
    '--terminal-tab-hover-color': option.color,
    '--terminal-tab-active-bg': option.activeBackground,
    '--terminal-tab-active-color': option.activeColor,
    '--terminal-tab-active-border': option.activeBorder,
  };
}

function setTerminalTabColor(tab: TerminalTab, colorId: TerminalTabColorId | null) {
  tab.colorId = colorId;
  saveTerminalWorkspace();
}

function renameTerminalTab(tab: TerminalTab) {
  const nextTitle = window.prompt('重命名标签名称', getTerminalTabLabel(tab));
  if (nextTitle === null) return;
  const normalized = normalizeTerminalTabTitle(nextTitle);
  if (!normalized) return;
  tab.customTitle = normalized === tab.host.name ? '' : normalized;
  saveTerminalWorkspace();
}

function getTerminalTabsRightOf(tab: TerminalTab) {
  const index = tabs.value.findIndex((item) => item.id === tab.id);
  return index === -1 ? [] : tabs.value.slice(index + 1);
}

function sendQuickCommandToTerminalTab(command: TerminalQuickCommand, execute: boolean, tab: TerminalTab | null) {
  if (!command.enabled || !canSendQuickCommandToTab(tab)) return;
  const data = execute ? `${command.command}\r` : command.command;
  if (isTerminalMultiExecutionEnabled.value) {
    sendTerminalInputToMultiExecutionTargets(data);
    return;
  }
  sendTerminalInput(tab, data, { focus: true });
}

function getTerminalTabQuickCommandItems(tab: TerminalTab | null): TerminalContextMenuItem[] {
  const items: TerminalContextMenuItem[] = [
    {
      id: 'tab-quick-panel',
      label: isTerminalQuickCommandPanelCollapsed.value ? '展开快捷命令面板' : '收起快捷命令面板',
      icon: 'zap',
      enabled: shouldShowTerminalQuickCommandPanel.value,
      action: () => toggleTerminalQuickCommandPanel(),
    },
    { id: 'tab-quick-new', label: '新增命令...', icon: 'plus', enabled: canUseTerminalQuickCommands.value, action: () => openTerminalQuickCommandDialog() },
  ];
  const commands = terminalQuickCommands.value.filter((command) => command.enabled).slice(0, 6);
  if (!commands.length) {
    items.push({ id: 'tab-quick-empty', label: '暂无可用快捷命令', icon: 'terminal', enabled: false, separatorBefore: true, action: () => undefined });
    return items;
  }
  for (const command of commands) {
    items.push(
      {
        id: `tab-quick-append-${command.id}`,
        label: `追加：${command.name}`,
        icon: 'cornerDownLeft',
        enabled: canSendQuickCommandToTab(tab),
        separatorBefore: items.length === 2,
        action: () => sendQuickCommandToTerminalTab(command, false, tab),
      },
      {
        id: `tab-quick-run-${command.id}`,
        label: `执行：${command.name}`,
        icon: 'zap',
        enabled: canSendQuickCommandToTab(tab),
        action: () => sendQuickCommandToTerminalTab(command, true, tab),
      },
    );
  }
  return items;
}

function cssEscape(value: string) {
  const escape = window.CSS?.escape;
  return escape ? escape(value) : value.replace(/["\\]/g, '\\$&');
}


function toggleTerminalTabMenu() {
  isTerminalTabMenuOpen.value = !isTerminalTabMenuOpen.value;
  if (isTerminalTabMenuOpen.value) {
    closeTerminalContextMenu();
    closeTerminalTabContextMenu();
    closeTerminalSplitMenu();
  }
}

function closeTerminalTabMenu() {
  isTerminalTabMenuOpen.value = false;
}

function toggleTerminalSplitMenu() {
  isTerminalSplitMenuOpen.value = !isTerminalSplitMenuOpen.value;
  if (isTerminalSplitMenuOpen.value) {
    closeTerminalContextMenu();
    closeTerminalTabContextMenu();
    closeTerminalTabMenu();
  }
}

function closeTerminalSplitMenu() {
  isTerminalSplitMenuOpen.value = false;
}

function setTerminalSplitMode(mode: TerminalSplitMode) {
  terminalSplitMode.value = mode;
  window.localStorage.setItem(TERMINAL_SPLIT_MODE_STORAGE_KEY, mode);
  closeTerminalSplitMenu();
  fitVisibleTerminalsSoon();
}

function syncTerminalTabsScrollState() {
  const tabsElement = terminalTabsRef.value;
  if (!tabsElement) {
    canScrollTerminalTabsLeft.value = false;
    canScrollTerminalTabsRight.value = false;
    return;
  }

  const maxScrollLeft = Math.max(0, tabsElement.scrollWidth - tabsElement.clientWidth);
  canScrollTerminalTabsLeft.value = tabsElement.scrollLeft > 1;
  canScrollTerminalTabsRight.value = tabsElement.scrollLeft < maxScrollLeft - 1;
}

function syncTerminalTabsScrollStateSoon() {
  window.requestAnimationFrame(syncTerminalTabsScrollState);
}

function scrollTerminalTabs(direction: 'left' | 'right') {
  const tabsElement = terminalTabsRef.value;
  if (!tabsElement) return;
  const distance = Math.max(120, tabsElement.clientWidth * 0.7);
  tabsElement.scrollBy({
    left: direction === 'left' ? -distance : distance,
    behavior: 'smooth',
  });
  window.setTimeout(syncTerminalTabsScrollState, 220);
}

function scrollActiveTerminalTabIntoView() {
  const tabsElement = terminalTabsRef.value;
  if (!tabsElement || !activeTabId.value) {
    syncTerminalTabsScrollStateSoon();
    return;
  }
  const activeButton = tabsElement.querySelector<HTMLElement>(`[data-terminal-tab-id="${cssEscape(activeTabId.value)}"]`);
  activeButton?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
  window.setTimeout(syncTerminalTabsScrollState, 220);
}

function createTerminalQuickCommandDraft(command?: TerminalQuickCommand | null): TerminalQuickCommandDraft {
  return {
    name: command?.name ?? '',
    category: command?.category ?? terminalQuickCommands.value[0]?.category ?? 'Linux',
    command: command?.command ?? '',
    description: command?.description ?? '',
    enabled: command?.enabled ?? true,
    sortOrder: command?.sortOrder ?? 0,
  };
}

async function loadTerminalQuickCommands() {
  isTerminalQuickCommandLoading.value = true;
  terminalQuickCommandError.value = '';
  try {
    terminalQuickCommands.value = await listTerminalQuickCommands();
    if (
      terminalQuickCommandCategory.value !== 'all' &&
      !terminalQuickCommands.value.some((command) => command.category === terminalQuickCommandCategory.value)
    ) {
      terminalQuickCommandCategory.value = 'all';
    }
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    terminalQuickCommandError.value = error instanceof Error ? error.message : '快捷命令加载失败';
  } finally {
    isTerminalQuickCommandLoading.value = false;
  }
}

function openTerminalQuickCommandDialog(command: TerminalQuickCommand | null = null) {
  terminalQuickCommandDialog.value = {
    visible: true,
    mode: command ? 'edit' : 'create',
    commandId: command?.id ?? null,
    draft: createTerminalQuickCommandDraft(command),
    saving: false,
    error: '',
  };
}

function closeTerminalQuickCommandDialog() {
  if (terminalQuickCommandDialog.value.saving) return;
  terminalQuickCommandDialog.value = {
    visible: false,
    mode: 'create',
    commandId: null,
    draft: createTerminalQuickCommandDraft(),
    saving: false,
    error: '',
  };
}

function terminalQuickCommandPayload(draft: TerminalQuickCommandDraft) {
  return {
    name: draft.name.trim(),
    category: draft.category.trim(),
    command: draft.command.trim(),
    description: draft.description.trim(),
    enabled: draft.enabled,
    sortOrder: draft.sortOrder,
  };
}

async function saveTerminalQuickCommandDialog() {
  const dialog = terminalQuickCommandDialog.value;
  if (!dialog.visible || dialog.saving) return;
  const payload = terminalQuickCommandPayload(dialog.draft);
  if (!payload.name || !payload.category || !payload.command) {
    terminalQuickCommandDialog.value = { ...dialog, error: '请填写名称、分类和命令内容' };
    return;
  }

  terminalQuickCommandDialog.value = { ...dialog, saving: true, error: '' };
  try {
    const saved =
      dialog.mode === 'edit' && dialog.commandId
        ? await updateTerminalQuickCommand(dialog.commandId, payload)
        : await createTerminalQuickCommand(payload);
    const nextCommands =
      dialog.mode === 'edit'
        ? terminalQuickCommands.value.map((command) => (command.id === saved.id ? saved : command))
        : [...terminalQuickCommands.value, saved];
    terminalQuickCommands.value = sortTerminalQuickCommands(nextCommands);
    terminalQuickCommandCategory.value = saved.category;
    closeTerminalQuickCommandDialog();
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    terminalQuickCommandDialog.value = {
      ...dialog,
      saving: false,
      error: error instanceof Error ? error.message : '快捷命令保存失败',
    };
  }
}

async function deleteTerminalQuickCommand(command: TerminalQuickCommand) {
  if (!window.confirm(`删除快捷命令“${command.name}”？`)) return;
  try {
    await removeTerminalQuickCommand(command.id);
    terminalQuickCommands.value = terminalQuickCommands.value.filter((item) => item.id !== command.id);
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    terminalQuickCommandError.value = error instanceof Error ? error.message : '快捷命令删除失败';
  }
}

async function toggleTerminalQuickCommand(command: TerminalQuickCommand) {
  try {
    const saved = await updateTerminalQuickCommand(command.id, {
      ...command,
      enabled: !command.enabled,
    });
    terminalQuickCommands.value = terminalQuickCommands.value.map((item) => (item.id === saved.id ? saved : item));
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    terminalQuickCommandError.value = error instanceof Error ? error.message : '快捷命令状态更新失败';
  }
}

async function moveTerminalQuickCommand(command: TerminalQuickCommand, direction: -1 | 1) {
  const visibleCommands = filteredTerminalQuickCommands.value;
  const visibleIndex = visibleCommands.findIndex((item) => item.id === command.id);
  const target = visibleCommands[visibleIndex + direction];
  if (!target) return;

  const nextCommands = [...terminalQuickCommands.value];
  const sourceIndex = nextCommands.findIndex((item) => item.id === command.id);
  const targetIndex = nextCommands.findIndex((item) => item.id === target.id);
  if (sourceIndex === -1 || targetIndex === -1) return;

  [nextCommands[sourceIndex], nextCommands[targetIndex]] = [nextCommands[targetIndex], nextCommands[sourceIndex]];
  await saveTerminalQuickCommandOrder(nextCommands);
}

async function saveTerminalQuickCommandOrder(nextCommands: TerminalQuickCommand[]) {
  const previousCommands = terminalQuickCommands.value;
  terminalQuickCommands.value = nextCommands.map((command, index) => ({ ...command, sortOrder: (index + 1) * 10 }));
  try {
    terminalQuickCommands.value = await reorderTerminalQuickCommands(terminalQuickCommands.value.map((command) => command.id));
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    terminalQuickCommands.value = previousCommands;
    terminalQuickCommandError.value = error instanceof Error ? error.message : '快捷命令排序保存失败';
  }
}

function sortTerminalQuickCommands(commands: TerminalQuickCommand[]) {
  return [...commands].sort(
    (left, right) =>
      left.category.localeCompare(right.category, 'zh-Hans-CN') ||
      left.sortOrder - right.sortOrder ||
      left.id - right.id,
  );
}

function isTerminalAuthError(error: unknown) {
  return error instanceof ApiUnauthorizedError;
}

function handleTerminalAuthExpired(error?: unknown) {
  if (error && !isTerminalAuthError(error)) return false;
  if (terminalAuthRedirecting) return true;
  terminalAuthRedirecting = true;
  stopTerminalMonitorPolling();
  pendingConnectTabIds.splice(0, pendingConnectTabIds.length);
  connectingTabIds.clear();
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(TERMINAL_WORKSPACE_STORAGE_KEY);
  }
  for (const tab of tabs.value) {
    tab.status = 'closed';
    stopTerminalHeartbeat(tab.id);
    if (tab.socket && tab.socket.readyState !== WebSocket.CLOSED) {
      tab.socket.close();
    }
    tab.socket = null;
    cleanupRdpClient(tab);
  }
  window.location.replace('/');
  return true;
}

function handleTerminalAuthStorageEvent(event: StorageEvent) {
  if (event.key === AUTH_LOGOUT_EVENT_KEY) {
    handleTerminalAuthExpired();
  }
}

function sendQuickCommandToTerminal(command: TerminalQuickCommand, execute: boolean) {
  if (!command.enabled) return;
  const data = execute ? `${command.command}\r` : command.command;
  if (isTerminalMultiExecutionEnabled.value) {
    sendTerminalInputToMultiExecutionTargets(data);
    return;
  }
  if (!activeTerminalReady.value || !activeTab.value) return;
  sendTerminalInput(activeTab.value, data, { focus: true });
}

function closeTerminalContextMenus() {
  closeTerminalContextMenu();
  closeTerminalTabContextMenu();
  closeTerminalPastePrompt();
  closeTerminalTabMenu();
  closeTerminalSplitMenu();
}

async function selectTerminalTabFromMenu(tab: TerminalTab) {
  closeTerminalTabMenu();
  await activateTab(tab.id);
}

async function runTerminalContextMenuItem(item: TerminalContextMenuItem) {
  if (!item.enabled) return;
  if (item.children?.length) return;
  closeTerminalContextMenus();
  await item.action();
}

async function runTerminalTabContextMenuItem(item: TerminalContextMenuItem) {
  if (!item.enabled) return;
  if (item.children?.length) return;
  closeTerminalContextMenus();
  await item.action();
}

function openTerminalTabContextMenu(tab: TerminalTab, event: MouseEvent) {
  if (tab.id !== activeTabId.value) {
    void activateTab(tab.id);
  }
  closeTerminalContextMenu();
  closeTerminalTabMenu();
  closeTerminalSplitMenu();
  terminalTabContextMenu.value = {
    visible: true,
    tabId: tab.id,
    x: event.clientX,
    y: event.clientY,
  };
}

function openTerminalContextMenu(tab: TerminalTab, event: MouseEvent) {
  if (!isTerminalTabVisible(tab)) {
    event.preventDefault();
    return;
  }
  if (tab.id !== activeTabId.value) {
    void activateTab(tab.id);
  }
  const selectedText = tab.kind === 'ssh' && tab.terminal.hasSelection() ? tab.terminal.getSelection() : '';
  closeTerminalTabContextMenu();
  closeTerminalTabMenu();
  closeTerminalSplitMenu();
  terminalContextMenu.value = {
    visible: true,
    tabId: tab.id,
    selectedText,
    x: event.clientX,
    y: event.clientY,
  };
}



function closeTerminalContextMenu() {
  if (!terminalContextMenu.value.visible) return;
  terminalContextMenu.value = { visible: false, x: 0, y: 0, tabId: null, selectedText: '' };
}

function closeTerminalTabContextMenu() {
  if (!terminalTabContextMenu.value.visible) return;
  terminalTabContextMenu.value = { visible: false, x: 0, y: 0, tabId: null };
}

function getTerminalContextMenuTab() {
  const tabId = terminalContextMenu.value.tabId;
  return tabId ? getTabById(tabId) : activeTab.value;
}

function getTerminalTabContextMenuTab() {
  const tabId = terminalTabContextMenu.value.tabId;
  return tabId ? getTabById(tabId) : activeTab.value;
}

function isTerminalTabReady(tab: TerminalTab | null): tab is TerminalTab {
  return Boolean(tab && tab.kind === 'ssh' && tab.status === 'connected' && tab.socket?.readyState === WebSocket.OPEN);
}

function isSshTerminalTab(tab: TerminalTab | null): tab is TerminalTab {
  return Boolean(tab && tab.kind === 'ssh');
}

function canDisconnectTerminalTab(tab: TerminalTab | null) {
  return Boolean(tab && (tab.status === 'connecting' || tab.status === 'connected' || tab.socket || tab.guacClient));
}

async function copyTerminalContextText(value: string) {
  if (!value) return;
  await writeTextToClipboard(value);
}

async function pasteClipboardToTerminal(tab: TerminalTab | null, x?: number, y?: number) {
  if (!isTerminalTabReady(tab)) return;
  let value = '';
  try {
    value = (await navigator.clipboard?.readText()) ?? '';
  } catch {
    // Browser clipboard reads are blocked on insecure HTTP origins.
  }
  if (value) {
    sendPastedTextToTerminal(value, tab);
    return;
  }
  openTerminalPastePrompt(tab, x, y);
}

function openTerminalPastePrompt(tab: TerminalTab, x = window.innerWidth / 2 - 160, y = window.innerHeight / 2 - 80) {
  const padding = 12;
  terminalPastePrompt.value = {
    visible: true,
    x: Math.max(padding, Math.min(x, window.innerWidth - 340)),
    y: Math.max(padding, Math.min(y, window.innerHeight - 156)),
    tabId: tab.id,
    value: '',
  };
  void nextTick(() => terminalPasteInputRef.value?.focus());
}

function closeTerminalPastePrompt() {
  terminalPastePrompt.value = { visible: false, x: 0, y: 0, tabId: null, value: '' };
}

function submitTerminalPastePrompt(value = terminalPastePrompt.value.value) {
  const tab = terminalPastePrompt.value.tabId ? getTabById(terminalPastePrompt.value.tabId) : activeTab.value;
  if (value && isTerminalTabReady(tab)) sendPastedTextToTerminal(value, tab);
  closeTerminalPastePrompt();
}

function handleTerminalPastePromptPaste(event: ClipboardEvent) {
  const value = getClipboardTextFromPasteEvent(event);
  if (value) submitTerminalPastePrompt(value);
}

function sendTextToTerminal(value: string, tab: TerminalTab | null) {
  sendTerminalInput(tab, value, { focus: true });
}

function sendPastedTextToTerminal(value: string, tab: TerminalTab | null) {
  sendTextToTerminal(normalizeTerminalPasteText(value), tab);
}

function sendControlToTerminal(value: string, tab: TerminalTab | null) {
  sendTextToTerminal(value, tab);
}

function sendPastedTextToMultiExecutionTargets(value: string) {
  sendTerminalInputToMultiExecutionTargets(normalizeTerminalPasteText(value));
}

function toSingleLineTerminalText(value: string) {
  return value.replace(/[\r\n]+/g, ' ').replace(/\s+/g, ' ').trim();
}

function openTerminalOnlineSearch(query: string) {
  const value = query.trim();
  if (!value) return;
  window.open(`https://www.bing.com/search?q=${encodeURIComponent(value)}`, '_blank', 'noopener,noreferrer');
}

function openTerminalTranslation(text: string, targetLanguage: 'zh-Hans' | 'en') {
  const value = text.trim();
  if (!value) return;
  window.open(
    `https://www.bing.com/translator?to=${encodeURIComponent(targetLanguage)}&text=${encodeURIComponent(value)}`,
    '_blank',
    'noopener,noreferrer',
  );
}

function findTerminalText(query: string) {
  const value = query.trim();
  if (!value) return;
  openTerminalSearch(value);
}

function promptFindTerminalText() {
  openTerminalSearch();
}

function getTerminalSearchOptions(incremental = false): ISearchOptions {
  return {
    caseSensitive: false,
    incremental,
    decorations: TERMINAL_SEARCH_DECORATIONS,
  };
}

function resetTerminalSearchResultState() {
  terminalSearchResultIndex.value = -1;
  terminalSearchResultCount.value = 0;
}

function focusTerminalSearchInputSoon(select = false) {
  void nextTick(() => {
    const input = terminalSearchInputRef.value;
    if (!input) return;
    input.focus();
    if (select) input.input?.select();
  });
}

function openTerminalSearch(initialQuery = '') {
  if (!isSshTerminalTab(activeTab.value)) return;
  closeTerminalContextMenus();
  isTerminalSearchOpen.value = true;
  if (initialQuery.trim()) {
    terminalSearchQuery.value = initialQuery.trim();
  }
  resetTerminalSearchResultState();
  focusTerminalSearchInputSoon(!initialQuery.trim());
  if (terminalSearchQuery.value.trim()) {
    void nextTick(() => searchCurrentTerminal('next', true));
  }
}

function clearTerminalSearchDecorations(tab: TerminalTab | null = activeTab.value) {
  if (tab?.kind === 'ssh') tab.searchAddon.clearDecorations();
}

function clearAllTerminalSearchDecorations() {
  for (const tab of tabs.value) clearTerminalSearchDecorations(tab);
}

function closeTerminalSearch() {
  if (!isTerminalSearchOpen.value) return;
  isTerminalSearchOpen.value = false;
  clearAllTerminalSearchDecorations();
  resetTerminalSearchResultState();
  if (activeTab.value?.kind === 'ssh') activeTab.value.terminal.focus();
}

function searchCurrentTerminal(direction: 'next' | 'previous' = 'next', incremental = false) {
  const query = terminalSearchQuery.value.trim();
  const tab = activeTab.value;
  if (!isSshTerminalTab(tab)) {
    resetTerminalSearchResultState();
    return false;
  }
  if (!query) {
    clearTerminalSearchDecorations(tab);
    tab.terminal.clearSelection();
    resetTerminalSearchResultState();
    return false;
  }
  clearTerminalSearchDecorations(tab);
  const matches = collectTerminalSearchMatches(tab, query);
  terminalSearchResultCount.value = matches.length;
  if (!matches.length) {
    terminalSearchResultIndex.value = -1;
    tab.terminal.clearSelection();
    return false;
  }

  const currentIndex = terminalSearchResultIndex.value;
  const nextIndex =
    incremental || currentIndex < 0
      ? 0
      : direction === 'previous'
        ? (currentIndex - 1 + matches.length) % matches.length
        : (currentIndex + 1) % matches.length;
  terminalSearchResultIndex.value = nextIndex;
  decorateTerminalSearchMatches(tab, query);
  selectTerminalSearchMatch(tab, matches[nextIndex]);
  return true;
}

function decorateTerminalSearchMatches(tab: TerminalTab, query: string) {
  try {
    tab.searchAddon.findNext(query, getTerminalSearchOptions(false));
  } catch {
    // The buffer scan above is the source of truth; addon decorations are best-effort.
  }
}

function selectTerminalSearchMatch(tab: TerminalTab, match: TerminalSearchMatch | undefined) {
  if (!match) return;
  const buffer = tab.terminal.buffer.active;
  if (match.row < buffer.viewportY || match.row >= buffer.viewportY + tab.terminal.rows) {
    tab.terminal.scrollToLine(Math.max(0, match.row - Math.floor(tab.terminal.rows / 2)));
  }
  tab.terminal.select(match.col, match.row, match.size);
}

function collectTerminalSearchMatches(tab: TerminalTab, query: string) {
  const normalizedQuery = query.toLowerCase();
  const matches: TerminalSearchMatch[] = [];
  if (!normalizedQuery) return matches;

  const buffer = tab.terminal.buffer.active;
  const maxRow = buffer.baseY + tab.terminal.rows;
  for (let row = 0; row < maxRow; row += 1) {
    const line = buffer.getLine(row);
    if (!line || line.isWrapped) continue;

    const logicalLine = getTerminalLogicalSearchLine(tab, row, maxRow);
    const searchText = logicalLine.text.toLowerCase();
    let index = searchText.indexOf(normalizedQuery);
    while (index !== -1) {
      const position = getTerminalSearchBufferPosition(logicalLine.parts, index);
      if (position) {
        matches.push({
          row: position.row,
          col: position.col,
          size: Math.max(1, query.length),
        });
      }
      index = searchText.indexOf(normalizedQuery, index + Math.max(1, normalizedQuery.length));
    }
  }
  return matches;
}

function getTerminalLogicalSearchLine(tab: TerminalTab, startRow: number, maxRow: number) {
  const parts: Array<{ row: number; line: IBufferLine; start: number; text: string }> = [];
  const buffer = tab.terminal.buffer.active;
  let text = '';
  for (let row = startRow; row < maxRow; row += 1) {
    const line = buffer.getLine(row);
    if (!line) break;
    const nextLine = row + 1 < maxRow ? buffer.getLine(row + 1) : undefined;
    const lineText = line.translateToString(!nextLine?.isWrapped);
    parts.push({ row, line, start: text.length, text: lineText });
    text += lineText;
    if (!nextLine?.isWrapped) break;
  }
  return { text, parts };
}

function getTerminalSearchBufferPosition(
  parts: Array<{ row: number; line: IBufferLine; start: number; text: string }>,
  stringIndex: number,
) {
  for (const part of parts) {
    if (stringIndex < part.start || stringIndex >= part.start + part.text.length) continue;
    return {
      row: part.row,
      col: getTerminalColumnFromStringOffset(part.line, stringIndex - part.start),
    };
  }
  return null;
}

function getTerminalColumnFromStringOffset(line: IBufferLine, offset: number) {
  let consumed = 0;
  for (let col = 0; col < line.length; col += 1) {
    const cell = line.getCell(col);
    if (!cell || cell.getWidth() === 0) continue;
    const chars = cell.getChars() || ' ';
    const nextConsumed = consumed + chars.length;
    if (offset <= consumed || offset < nextConsumed) return col;
    consumed = nextConsumed;
  }
  return Math.max(0, Math.min(line.length - 1, offset));
}

function openTerminalQuickCommandDialogFromText(commandText: string) {
  const command = commandText.trim();
  if (!command) return;
  const firstLine = command.split(/\r?\n/).find(Boolean) ?? '快捷命令';
  terminalQuickCommandDialog.value = {
    visible: true,
    mode: 'create',
    commandId: null,
    draft: {
      ...createTerminalQuickCommandDraft(),
      name: firstLine.slice(0, 40),
      command,
      description: '从终端选中内容保存',
      enabled: true,
    },
    saving: false,
    error: '',
  };
  if (isTerminalQuickCommandPanelCollapsed.value && shouldShowTerminalQuickCommandPanel.value) {
    toggleTerminalQuickCommandPanel();
  }
}

function getTerminalQuickCommandContextItems(tab: TerminalTab | null): TerminalContextMenuItem[] {
  const items: TerminalContextMenuItem[] = [
    {
      id: 'quick-panel',
      label: isTerminalQuickCommandPanelCollapsed.value ? '展开快捷命令面板' : '收起快捷命令面板',
      icon: 'zap',
      enabled: shouldShowTerminalQuickCommandPanel.value,
      action: () => toggleTerminalQuickCommandPanel(),
    },
    { id: 'quick-new', label: '新增命令...', icon: 'plus', enabled: canUseTerminalQuickCommands.value, action: () => openTerminalQuickCommandDialog() },
  ];
  const commands = terminalQuickCommands.value.filter((command) => command.enabled).slice(0, 6);
  for (const command of commands) {
    items.push({
      id: `quick-${command.id}`,
      label: command.name,
      icon: 'terminal',
      enabled: canSendQuickCommandToTab(tab),
      separatorBefore: items.length === 2,
      action: () => sendQuickCommandToTerminal(command, false),
    });
  }
  return items;
}

function getTerminalSessionContextMenu(tab: TerminalTab | null): TerminalContextMenuItem {
  return {
    id: 'session',
    label: '会话',
    icon: 'server',
    enabled: Boolean(tab),
    separatorBefore: true,
    action: () => undefined,
    children: [
      {
        id: 'session-reconnect',
        label: '重新连接',
        icon: 'refresh',
        enabled: Boolean(tab && (tab.status === 'closed' || tab.status === 'error')),
        action: () => {
          if (tab) reconnectTerminalTab(tab);
        },
      },
      {
        id: 'session-copy-info',
        label: '复制当前主机信息',
        icon: 'copy',
        enabled: Boolean(tab),
        action: async () => {
          if (tab) await copyTerminalContextText(getTerminalSessionInfo(tab));
        },
      },
      {
        id: 'session-duplicate',
        label: '新建同主机标签',
        icon: 'plus',
        enabled: Boolean(tab),
        action: async () => {
          if (tab) await openHostTab(tab.host);
        },
      },
      {
        id: 'session-close',
        label: '关闭当前标签',
        icon: 'x',
        enabled: Boolean(tab),
        danger: true,
        separatorBefore: true,
        action: async () => {
          if (tab) await closeTab(tab);
        },
      },
    ],
  };
}

function getTerminalControlKeyContextMenu(tab: TerminalTab | null): TerminalContextMenuItem {
  const enabled = isTerminalTabReady(tab);
  return {
    id: 'control-keys',
    label: '发送控制键',
    icon: 'terminal',
    enabled,
    action: () => undefined,
    children: [
      { id: 'control-c', label: '中断', icon: 'x', enabled, shortcut: 'Ctrl+C', action: () => sendControlToTerminal('\x03', tab) },
      { id: 'control-d', label: 'EOF', icon: 'logout', enabled, shortcut: 'Ctrl+D', action: () => sendControlToTerminal('\x04', tab) },
      { id: 'control-z', label: '挂起', icon: 'minimize', enabled, shortcut: 'Ctrl+Z', action: () => sendControlToTerminal('\x1a', tab) },
      { id: 'control-u', label: '清空当前输入', icon: 'trash', enabled, shortcut: 'Ctrl+U', action: () => sendControlToTerminal('\x15', tab) },
      { id: 'control-l', label: '清屏', icon: 'rows', enabled, shortcut: 'Ctrl+L', action: () => sendControlToTerminal('\x0c', tab) },
    ],
  };
}

function getTerminalViewContextMenu(tab: TerminalTab | null): TerminalContextMenuItem {
  const filePanelOpen = terminalSidebarMode.value === 'files' && !isTerminalSidebarCollapsed.value;
  const sshTab = isSshTerminalTab(tab);
  const splitItems: TerminalContextMenuItem[] = terminalSplitModeOptions.map((option, index) => ({
    id: `split-${option.mode}`,
    label: terminalSplitMode.value === option.mode ? `${option.label} ✓` : option.label,
    icon: option.icon,
    enabled: true,
    separatorBefore: index === 0,
    action: () => setTerminalSplitMode(option.mode),
  }));
  return {
    id: 'view',
    label: '视图',
    icon: 'settings',
    enabled: true,
    action: () => undefined,
    children: [
      { id: 'view-files', label: filePanelOpen ? '关闭文件面板' : '打开文件面板', icon: 'folder', enabled: sshTab, action: () => toggleTerminalFilePanel() },
      { id: 'view-monitor', label: isTerminalMonitorPanelOpen.value ? '关闭资源监控' : '打开资源监控', icon: 'monitor', enabled: sshTab, action: () => toggleTerminalMonitorPanel() },
      ...splitItems,
      { id: 'font-decrease', label: '字号减小', icon: 'zoomOut', enabled: canDecreaseTerminalFontSize.value, separatorBefore: true, action: () => decreaseTerminalFontSize() },
      { id: 'font-increase', label: '字号增大', icon: 'zoomIn', enabled: canIncreaseTerminalFontSize.value, action: () => increaseTerminalFontSize() },
      { id: 'font-reset', label: '重置字号', icon: 'reset', enabled: terminalFontSize.value !== TERMINAL_FONT_SIZE_DEFAULT, action: () => setTerminalFontSize(TERMINAL_FONT_SIZE_DEFAULT) },
      { id: 'highlight-toggle', label: highlightEnabled.value ? '关闭高亮' : '开启高亮', icon: 'sun', enabled: true, separatorBefore: true, action: () => { highlightEnabled.value = !highlightEnabled.value; } },
    ],
  };
}

function getTerminalBufferContextMenu(tab: TerminalTab | null): TerminalContextMenuItem {
  const hasTab = isSshTerminalTab(tab);
  const ready = isTerminalTabReady(tab);
  return {
    id: 'buffer',
    label: '缓冲区',
    icon: 'rows',
    enabled: hasTab,
    action: () => undefined,
    children: [
      { id: 'buffer-clear-screen', label: '清屏', icon: 'rows', enabled: ready, shortcut: 'Ctrl+L', action: () => sendControlToTerminal('\x0c', tab) },
      { id: 'buffer-clear-all', label: '全部清除', icon: 'trash', enabled: hasTab, action: () => tab?.terminal.clear() },
      { id: 'buffer-bottom', label: '滚动到底部', icon: 'chevronDown', enabled: hasTab, action: () => tab?.terminal.scrollToBottom() },
      {
        id: 'buffer-copy-screen',
        label: '复制当前屏幕',
        icon: 'copy',
        enabled: hasTab,
        separatorBefore: true,
        action: async () => {
          if (tab) await copyTerminalContextText(getTerminalVisibleText(tab));
        },
      },
      {
        id: 'buffer-export',
        label: '导出终端日志...',
        icon: 'download',
        enabled: hasTab,
        action: () => {
          if (tab) exportTerminalLog(tab);
        },
      },
      { id: 'buffer-select-all', label: '全选', icon: 'scan', enabled: hasTab, shortcut: 'Ctrl+Shift+A', separatorBefore: true, action: () => tab?.terminal.selectAll() },
    ],
  };
}

function writeTerminalTextFromSftp(value: string) {
  if (!value || !activeTab.value) return;
  activeTab.value.terminal.write(value);
  activeTab.value.terminal.focus();
}

function toggleTerminalFilePanel() {
  if (!activeTerminalSupportsSshTools.value) return;
  if (terminalSidebarMode.value === 'files' && !isTerminalSidebarCollapsed.value) {
    setTerminalSidebarCollapsed(true);
    return;
  }
  selectTerminalSidebarMode('files');
}

function getTerminalSessionInfo(tab: TerminalTab) {
  const host = tab.host;
  return [
    `主机：${host.name}`,
    `登录用户：${host.loginUser || '-'}`,
    `公网 IP：${host.publicIp || '-'}`,
    `内网 IP：${host.privateIp || '-'}`,
    `端口：${host.port}`,
    `当前目录：${tab.currentCwd || '-'}`,
    `状态：${tab.status}`,
  ].join('\n');
}

function getTerminalVisibleText(tab: TerminalTab) {
  const buffer = tab.terminal.buffer.active;
  const start = buffer.viewportY;
  const end = Math.min(buffer.length, start + tab.terminal.rows);
  const lines: string[] = [];
  for (let index = start; index < end; index += 1) {
    lines.push(buffer.getLine(index)?.translateToString(true) ?? '');
  }
  return lines.join('\n').trimEnd();
}

function getTerminalBufferText(tab: TerminalTab) {
  const buffer = tab.terminal.buffer.active;
  const lines: string[] = [];
  for (let index = 0; index < buffer.length; index += 1) {
    lines.push(buffer.getLine(index)?.translateToString(true) ?? '');
  }
  return lines.join('\n').trimEnd();
}

function exportTerminalLog(tab: TerminalTab) {
  const content = getTerminalBufferText(tab);
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${sanitizeTerminalLogFileName(tab.host.name)}-${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function sanitizeTerminalLogFileName(value: string) {
  return value.trim().replace(/[<>:"/\\|?*\x00-\x1f]/g, '_') || 'terminal';
}

function toggleTerminalQuickCommandPanel() {
  isTerminalQuickCommandPanelCollapsed.value = !isTerminalQuickCommandPanelCollapsed.value;
  window.localStorage.setItem(
    TERMINAL_QUICK_COMMAND_PANEL_COLLAPSED_STORAGE_KEY,
    isTerminalQuickCommandPanelCollapsed.value ? '1' : '0',
  );
  fitActiveTerminalSoon();
}

function startTerminalQuickCommandPanelResize(event: MouseEvent) {
  if (event.button !== 0 || isTerminalQuickCommandPanelCollapsed.value) return;
  event.preventDefault();
  isTerminalQuickCommandPanelResizing.value = true;
  terminalQuickCommandResizeStartY = event.clientY;
  terminalQuickCommandResizeStartHeight = terminalQuickCommandPanelHeight.value;
  window.addEventListener('mousemove', resizeTerminalQuickCommandPanel);
  window.addEventListener('mouseup', stopTerminalQuickCommandPanelResize);
}

function resizeTerminalQuickCommandPanel(event: MouseEvent) {
  if (!isTerminalQuickCommandPanelResizing.value) return;
  const delta = terminalQuickCommandResizeStartY - event.clientY;
  const nextHeight = clampTerminalQuickCommandPanelHeight(terminalQuickCommandResizeStartHeight + delta);
  terminalQuickCommandPanelHeight.value = nextHeight;
  window.localStorage.setItem(TERMINAL_QUICK_COMMAND_PANEL_HEIGHT_STORAGE_KEY, String(nextHeight));
  fitActiveTerminalSoon();
}

function stopTerminalQuickCommandPanelResize() {
  if (!isTerminalQuickCommandPanelResizing.value) return;
  isTerminalQuickCommandPanelResizing.value = false;
  window.removeEventListener('mousemove', resizeTerminalQuickCommandPanel);
  window.removeEventListener('mouseup', stopTerminalQuickCommandPanelResize);
  fitActiveTerminalSoon();
}

function syncTerminalQuickCommandPanelHeight() {
  const nextHeight = clampTerminalQuickCommandPanelHeight(terminalQuickCommandPanelHeight.value);
  if (nextHeight !== terminalQuickCommandPanelHeight.value) {
    terminalQuickCommandPanelHeight.value = nextHeight;
    window.localStorage.setItem(TERMINAL_QUICK_COMMAND_PANEL_HEIGHT_STORAGE_KEY, String(nextHeight));
  }
}

function clampTerminalQuickCommandPanelHeight(height: number) {
  const viewportHeight = typeof window === 'undefined' ? 0 : window.innerHeight;
  const maxByViewport = viewportHeight ? Math.floor(viewportHeight * 0.46) : TERMINAL_QUICK_COMMAND_PANEL_MAX_HEIGHT;
  const maxHeight = Math.max(
    TERMINAL_QUICK_COMMAND_PANEL_MIN_HEIGHT,
    Math.min(TERMINAL_QUICK_COMMAND_PANEL_MAX_HEIGHT, maxByViewport),
  );
  return Math.min(Math.max(height, TERMINAL_QUICK_COMMAND_PANEL_MIN_HEIGHT), maxHeight);
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = String(reader.result || '');
      resolve(result.includes(',') ? result.split(',')[1] : result);
    };
    reader.onerror = () => reject(reader.error ?? new Error('文件读取失败'));
    reader.readAsDataURL(file);
  });
}

async function loadTerminalMonitor() {
  if (!isTerminalMonitorVisible()) {
    terminalMonitorRequestId += 1;
    isTerminalMonitorLoading.value = false;
    if (!activeTab.value) {
      terminalMonitorData.value = null;
      terminalMonitorError.value = '';
    }
    return;
  }

  const tab = activeTab.value;
  if (!tab) return;

  const requestId = ++terminalMonitorRequestId;
  isTerminalMonitorLoading.value = true;
  try {
    const response = await getTerminalMonitor(tab.host.id);
    if (requestId !== terminalMonitorRequestId) return;
    terminalMonitorData.value = response;
    terminalMonitorError.value = '';
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    if (requestId !== terminalMonitorRequestId) return;
    terminalMonitorError.value = error instanceof Error ? error.message : '资源监控读取失败';
  } finally {
    if (requestId === terminalMonitorRequestId) {
      isTerminalMonitorLoading.value = false;
    }
  }
}

function isTerminalMonitorVisible() {
  return (
    isTerminalMonitorPanelOpen.value &&
    document.visibilityState === 'visible' &&
    activeTerminalSupportsSshTools.value
  );
}

function syncTerminalMonitorPolling() {
  if (!isTerminalMonitorVisible()) {
    stopTerminalMonitorPolling();
    terminalMonitorRequestId += 1;
    isTerminalMonitorLoading.value = false;
    if (!activeTab.value) {
      terminalMonitorData.value = null;
      terminalMonitorError.value = '';
    }
    return;
  }

  void loadTerminalMonitor();
  startTerminalMonitorPolling();
}

function startTerminalMonitorPolling() {
  if (terminalMonitorTimer) return;
  terminalMonitorTimer = window.setInterval(() => {
    if (isTerminalMonitorVisible()) {
      void loadTerminalMonitor();
    } else {
      syncTerminalMonitorPolling();
    }
  }, TERMINAL_MONITOR_REFRESH_MS);
}

function stopTerminalMonitorPolling() {
  if (!terminalMonitorTimer) return;
  window.clearInterval(terminalMonitorTimer);
  terminalMonitorTimer = null;
}

function formatMonitorPercent(value: number) {
  return `${formatMonitorNumber(value, 1)}%`;
}

function formatMonitorNumber(value: number, digits = 1) {
  if (!Number.isFinite(value)) return '0';
  return Number(value).toFixed(digits).replace(/\.0$/, '');
}

function formatMonitorBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${formatMonitorNumber(value, unitIndex >= 3 ? 2 : 1)} ${units[unitIndex]}`;
}

function formatMonitorRate(bytesPerSecond: number) {
  return `${formatMonitorBytes(bytesPerSecond)}/s`;
}

function formatMonitorUptime(seconds: number) {
  const totalDays = Math.floor(Math.max(0, seconds) / 86400);
  if (totalDays >= 1) return `${totalDays}天`;
  const hours = Math.floor(Math.max(0, seconds) / 3600);
  if (hours >= 1) return `${hours}小时`;
  const minutes = Math.floor(Math.max(0, seconds) / 60);
  return `${minutes}分钟`;
}

function monitorProgressStyle(value: number): Record<string, string> {
  const percent = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return {
    '--value': String(percent),
    width: `${percent}%`,
  };
}

watch([activeTabId, terminalSidebarMode], () => {
  closeTerminalContextMenus();
  if (!activeTerminalSupportsSshTools.value && (terminalSidebarMode.value === 'files' || terminalSidebarMode.value === 'commands')) {
    terminalSidebarMode.value = 'hosts';
  }
  if (
    activeTerminalSupportsSshTools.value &&
    canUseTerminalQuickCommands.value &&
    terminalSidebarMode.value === 'commands' &&
    !terminalQuickCommands.value.length &&
    !isTerminalQuickCommandLoading.value
  ) {
    void loadTerminalQuickCommands();
  }
  syncTerminalMonitorPolling();
});

watch(activeTabId, (_tabId, previousTabId) => {
  terminalMonitorData.value = null;
  terminalMonitorError.value = '';
  if (previousTabId) clearTerminalSearchDecorations(getTabById(previousTabId));
  resetTerminalSearchResultState();
  if (!activeTerminalSupportsSshTools.value) {
    isTerminalSearchOpen.value = false;
    closeTerminalMonitorPanel();
    return;
  }
  if (isTerminalSearchOpen.value && terminalSearchQuery.value.trim()) {
    void nextTick(() => searchCurrentTerminal('next', true));
  }
});

watch(terminalSearchQuery, () => {
  if (!isTerminalSearchOpen.value) return;
  searchCurrentTerminal('next', true);
});

watch(isTerminalMonitorPanelOpen, () => {
  syncTerminalMonitorPolling();
  fitActiveTerminalSoon();
});

watch([terminalSplitMode, visibleTerminalTabs], () => {
  void nextTick(fitVisibleTerminalsSoon);
});

const terminalShellStyle = computed<Record<string, string>>(() => ({
  '--terminal-sidebar-width': `${isTerminalSidebarCollapsed.value ? 42 : sidebarWidth.value}px`,
  '--terminal-quick-command-height':
    !shouldShowTerminalQuickCommandPanel.value || isTerminalQuickCommandPanelCollapsed.value ? '0px' : `${terminalQuickCommandPanelHeight.value}px`,
}));
onMounted(async () => {
  window.addEventListener('click', closeTerminalContextMenus);
  window.addEventListener('keydown', closeTerminalContextMenusOnEscape);
  window.addEventListener('resize', syncTerminalSidebarWidth);
  window.addEventListener('resize', syncTerminalQuickCommandPanelHeight);
  window.addEventListener('resize', syncTerminalTabsScrollStateSoon);
  window.addEventListener('storage', handleTerminalAuthStorageEvent);
  document.addEventListener('visibilitychange', syncTerminalMonitorPolling);
  try {
    const current = await getCurrentUser();
    terminalCurrentUser.value = current.user;
    await loadTerminalSettings();
    if (canUseTerminalQuickCommands.value) await loadTerminalQuickCommands();
    await loadTree();
    if (terminalAuthRedirecting) return;
    await restoreTerminalWorkspace();
    const hostId = parseTerminalHostQuery(window.location.search);
    if (hostId) {
      const restoredTab = tabs.value.find((tab) => tab.host.id === hostId);
      if (restoredTab) {
        await activateTab(restoredTab.id);
      } else {
        const host = findHostById(groups.value, hostId);
        if (host) await openHostTab(host);
      }
    }
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    throw error;
  }
});

onBeforeUnmount(() => {
  stopSidebarResize();
  stopTerminalQuickCommandPanelResize();
  stopTerminalMonitorPolling();
  window.removeEventListener('click', closeTerminalContextMenus);
  window.removeEventListener('keydown', closeTerminalContextMenusOnEscape);
  window.removeEventListener('resize', syncTerminalSidebarWidth);
  window.removeEventListener('resize', syncTerminalQuickCommandPanelHeight);
  window.removeEventListener('resize', syncTerminalTabsScrollStateSoon);
  window.removeEventListener('storage', handleTerminalAuthStorageEvent);
  document.removeEventListener('visibilitychange', syncTerminalMonitorPolling);
  for (const tab of tabs.value) disposeTab(tab);
  terminalResize.disposeAll();
});

function closeTerminalContextMenusOnEscape(event: KeyboardEvent) {
  if ((event.target as Element | null)?.closest('.shadcn-context-menu-content')) return;
  const key = event.key.toLowerCase();
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === 'v') {
    event.preventDefault();
    void pasteClipboardToTerminal(activeTab.value);
    return;
  }
  if (event.key !== 'Escape') return;
  if (terminalPastePrompt.value.visible) {
    closeTerminalPastePrompt();
    return;
  }
  if (isTerminalSearchOpen.value) {
    closeTerminalSearch();
    return;
  }
  closeTerminalContextMenus();
}

async function loadTree() {
  isLoadingTree.value = true;
  treeError.value = '';
  try {
    groups.value = await listTerminalTree();
  } catch (error) {
    if (handleTerminalAuthExpired(error)) return;
    treeError.value = (error as Error).message;
  } finally {
    isLoadingTree.value = false;
  }
}

async function loadTerminalSettings() {
  const setting = await getSystemSettingOrNull(TERMINAL_SETTINGS_SETTING_KEY);
  terminalSettings.value = normalizeTerminalSettings(setting?.value);
  if (!window.localStorage.getItem(TERMINAL_FONT_SIZE_STORAGE_KEY)) {
    terminalFontSize.value = readTerminalFontSize();
  }
}

function toggleGroup(group: TerminalGroup) {
  const next = new Set(collapsed.value);
  if (next.has(group.id)) {
    next.delete(group.id);
  } else {
    next.add(group.id);
  }
  collapsed.value = next;
}

async function openHostTab(host: TerminalHost) {
  const createdTab = addTerminalTab(() => createTerminalTab(host));
  saveTerminalWorkspace();
  await nextTick();
  scrollActiveTerminalTabIntoView();
  const tab = getTabById(createdTab.id) ?? createdTab;
  mountTerminal(tab);
  enqueueConnectTab(tab);
}

function toggleRoot() {
  rootExpanded.value = !rootExpanded.value;
}

async function activateTab(tabId: string) {
  selectTerminalTab(tabId);
  saveTerminalWorkspace();
  await nextTick();
  scrollActiveTerminalTabIntoView();
  const tab = tabs.value.find((item) => item.id === tabId);
  if (tab) {
    tab.hasUnreadOutput = false;
    mountTerminal(tab);
    fitTerminal(tab);
    if (tab.kind === 'ssh') {
      tab.terminal.focus();
    } else {
      tab.guacDisplayElement?.focus();
    }
  }
}

function createTerminalTab(
  host: TerminalHost,
  tabId = createTerminalTabId(host.id),
  options: { customTitle?: string; colorId?: TerminalTabColorId | null } = {},
): TerminalTab {
  const kind = getTerminalHostProtocol(host);
  const terminal = markRaw(
    new Terminal({
      cursorBlink: true,
      convertEol: false,
      fontFamily: 'Consolas, "Courier New", monospace',
      fontSize: terminalFontSize.value,
      lineHeight: 1.25,
      scrollback: terminalSettings.value.scrollbackLines,
      theme: {
        background: '#000000',
        foreground: '#f5f7fb',
        cursor: '#f5f7fb',
        selectionBackground: '#7e22ce',
      },
    }),
  );
  const fitAddon = markRaw(new FitAddon());
  const searchAddon = markRaw(new SearchAddon({ highlightLimit: 2000 }));
  terminal.loadAddon(fitAddon);
  terminal.loadAddon(searchAddon);
  terminal.attachCustomKeyEventHandler((event) => handleTerminalKey(event, terminal));
  terminal.writeln(kind === 'rdp' ? 'CAPTAIN WEB RDP' : 'CAPTAIN WEB TERMINAL');
  terminal.writeln(`正在连接 ${host.name} (${host.publicIp || host.privateIp}:${host.port})...`);

  const tab: TerminalTab = {
    id: tabId,
    kind,
    host,
    customTitle: normalizeTerminalTabTitle(options.customTitle),
    colorId: normalizeTerminalTabColorId(options.colorId),
    status: 'connecting',
    terminal,
    fitAddon,
    searchAddon,
    socket: null,
    guacClient: null,
    guacTunnel: null,
    guacMouse: null,
    guacKeyboard: null,
    guacDisplayElement: null,
    rdpErrorMessage: '',
    sessionId: null,
    mounted: false,
    disposables: [],
    highlightState: {
      sgrActive: false,
      pendingControl: '',
    },
    suppressInterruptUntil: 0,
    hasUnreadOutput: false,
    currentCwd: '',
    reconnectHintShown: false,
  };
  return tab;
}

function createTerminalTabId(hostId: number) {
  return `${hostId}-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function getTerminalHostProtocol(host: TerminalHost): TerminalTabKind {
  const protocol = String(host.terminalProtocol || '').toLowerCase();
  const platform = String(host.platformType || host.os || '').toLowerCase();
  return protocol === 'rdp' || platform === 'windows' ? 'rdp' : 'ssh';
}

function handleTerminalKey(event: KeyboardEvent, terminal: Terminal) {
  const isCopyShortcut = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'c';
  if (!isCopyShortcut || !terminal.hasSelection()) return true;

  const selection = terminal.getSelection();
  if (selection) {
    void writeTextToClipboard(selection);
  }
  return false;
}

function suppressMouseInterrupt(tab: TerminalTab, duration: number) {
  tab.suppressInterruptUntil = Math.max(tab.suppressInterruptUntil, Date.now() + duration);
}

function markTerminalDoubleClick(tab: TerminalTab) {
  suppressMouseInterrupt(tab, MOUSE_DOUBLE_CLICK_INTERRUPT_SUPPRESSION_MS);
}

function getSendableTerminalData(tab: TerminalTab, data: string) {
  if (!data.includes(CONTROL_C) || Date.now() > tab.suppressInterruptUntil) return data;
  return data.split(CONTROL_C).join('');
}

function mountTerminal(tab: TerminalTab) {
  if (tab.mounted) return;
  const container = terminalContainers.get(tab.id);
  if (!container) return;
  if (tab.kind === 'rdp') {
    mountRdpTerminal(tab, container);
    return;
  }

  tab.terminal.open(container);
  tab.mounted = true;
  tab.disposables.push(attachTerminalPasteHandler(container, (value) => sendPastedTextToTerminal(value, tab)));
  tab.disposables.push(
    tab.terminal.onData((data) => {
      if (tab.status === 'closed' || tab.status === 'error') {
        if (data.includes('\r')) reconnectTerminalTab(tab);
        return;
      }
      if (tab.status === 'connecting') return;

      const sendableData = getSendableTerminalData(tab, data);
      if (!sendableData) return;

      if (sendTerminalInput(tab, sendableData)) {
        broadcastTerminalInputToMultiExecutionTargets(sendableData, tab);
      }
    }),
  );
  const handleMouseDown = (event: MouseEvent) => {
    if (event.button !== 0) return;
    suppressMouseInterrupt(tab, MOUSE_SELECTION_INTERRUPT_SUPPRESSION_MS);
    if (event.detail >= 2) markTerminalDoubleClick(tab);
  };
  const handleDoubleClick = () => markTerminalDoubleClick(tab);
  container.addEventListener('mousedown', handleMouseDown, true);
  container.addEventListener('dblclick', handleDoubleClick, true);
  tab.disposables.push({
    dispose: () => {
      container.removeEventListener('mousedown', handleMouseDown, true);
      container.removeEventListener('dblclick', handleDoubleClick, true);
    },
  });
  terminalResize.observe(tab, container);
  tab.terminal.focus();
}

function mountRdpTerminal(tab: TerminalTab, container: HTMLElement) {
  container.tabIndex = 0;
  container.textContent = '';
  tab.mounted = true;
  terminalResize.observe(tab, container);
  container.focus();
}

function enqueueConnectTab(tab: TerminalTab) {
  if (tab.status !== 'connecting' || pendingConnectTabIds.includes(tab.id) || connectingTabIds.has(tab.id)) return;
  pendingConnectTabIds.push(tab.id);
  drainConnectQueue();
}

function drainConnectQueue() {
  while (connectingTabIds.size < MAX_CONNECTING_TERMINALS && pendingConnectTabIds.length) {
    const tabId = pendingConnectTabIds.shift();
    if (!tabId) continue;

    const tab = getTabById(tabId);
    if (!tab || tab.status !== 'connecting') continue;

    connectingTabIds.add(tab.id);
    connectTab(tab);
  }
}

function finishConnectingTab(tab: TerminalTab) {
  if (!connectingTabIds.delete(tab.id)) return;
  drainConnectQueue();
}

function resetTerminalHighlightState(tab: TerminalTab) {
  tab.highlightState = {
    sgrActive: false,
    pendingControl: '',
  };
}

function showTerminalReconnectHint(tab: TerminalTab, reason = '') {
  if (tab.reconnectHintShown) return;
  if (reason) {
    tab.terminal.writeln(`\r\n\x1b[33m${reason}\x1b[0m`);
  }
  tab.terminal.writeln('\x1b[32m[会话已断开]\x1b[0m');
  tab.terminal.writeln('\x1b[32m[按回车键重新连接]\x1b[0m');
  tab.reconnectHintShown = true;
}

function reconnectTerminalTab(tab: TerminalTab) {
  if (terminalAuthRedirecting) return;
  if (tab.status !== 'closed' && tab.status !== 'error') return;
  tab.status = 'connecting';
  tab.sessionId = null;
  tab.currentCwd = '';
  tab.socket = null;
  cleanupRdpClient(tab);
  tab.reconnectHintShown = false;
  resetTerminalHighlightState(tab);
  removePendingConnectTab(tab.id);
  finishConnectingTab(tab);
  tab.terminal.writeln('\r\n\x1b[32m[正在重新连接...]\x1b[0m');
  enqueueConnectTab(tab);
}

function disconnectTerminalTab(tab: TerminalTab) {
  if (!canDisconnectTerminalTab(tab)) return;
  removePendingConnectTab(tab.id);
  finishConnectingTab(tab);
  sshTerminal.disconnect(tab);
  cleanupRdpClient(tab);
  tab.status = 'closed';
  showTerminalReconnectHint(tab, '连接已手动断开。');
}

const sshTerminal = useSshTerminal<TerminalTab>({
  buildUrl: (tab) => buildWebSocketUrl(tab.host.id),
  onOpen: fitTerminal,
  onMessage: handleSocketMessage,
  onError: (tab) => {
    stopTerminalHeartbeat(tab.id);
    if (tab.status !== 'closed') {
      tab.status = 'error';
      showTerminalReconnectHint(tab, 'WebSocket 连接失败。');
    }
    finishConnectingTab(tab);
  },
  onClose: (tab) => {
    stopTerminalHeartbeat(tab.id);
    finishConnectingTab(tab);
    if (tab.status === 'connected' || tab.status === 'connecting') {
      tab.status = 'closed';
      showTerminalReconnectHint(tab, '连接已关闭。');
      void confirmTerminalSessionStillAuthenticated();
    }
  },
});

function connectTab(tab: TerminalTab) {
  if (tab.kind === 'rdp') {
    connectRdpTab(tab);
    return;
  }
  if (terminalAuthRedirecting) return;
  tab.reconnectHintShown = false;
  sshTerminal.connect(tab);
}

function startTerminalHeartbeat(tab: TerminalTab) {
  stopTerminalHeartbeat(tab.id);
  const seconds = terminalSettings.value.webSocketHeartbeatSeconds;
  if (seconds <= 0) return;
  const timer = window.setInterval(() => {
    if (tab.socket?.readyState === WebSocket.OPEN) {
      tab.socket.send(JSON.stringify({ type: 'ping' }));
    }
  }, seconds * 1000);
  terminalHeartbeatTimers.set(tab.id, timer);
}

function stopTerminalHeartbeat(tabId: string) {
  const timer = terminalHeartbeatTimers.get(tabId);
  if (timer !== undefined) {
    window.clearInterval(timer);
    terminalHeartbeatTimers.delete(tabId);
  }
}

function connectRdpTab(tab: TerminalTab) {
  if (terminalAuthRedirecting) return;
  cleanupRdpClient(tab);
  tab.reconnectHintShown = false;
  tab.rdpErrorMessage = '';
  const tunnel = markRaw(new Guacamole.WebSocketTunnel(buildRdpWebSocketUrl(tab)));
  const client = markRaw(new Guacamole.Client(tunnel));
  tab.guacTunnel = tunnel;
  tab.guacClient = client;

  const container = terminalContainers.get(tab.id);
  const display = client.getDisplay();
  display.onresize = () => fitTerminal(tab);
  const displayElement = display.getElement();
  displayElement.classList.add('terminal-rdp-display');
  displayElement.tabIndex = 0;
  if (container) {
    container.textContent = '';
    container.appendChild(displayElement);
  }
  tab.guacDisplayElement = displayElement;
  attachRdpInputHandlers(tab, client, displayElement);

  client.onstatechange = (state) => {
    if (state === Guacamole.Client.State.CONNECTED) {
      tab.status = 'connected';
      finishConnectingTab(tab);
      fitTerminal(tab);
      if (tab.id !== activeTabId.value) markTabUnread(tab.id);
      return;
    }
    if (state === Guacamole.Client.State.DISCONNECTED && tab.status !== 'closed') {
      const wasConnecting = tab.status === 'connecting';
      tab.status = wasConnecting ? 'error' : 'closed';
      if (wasConnecting) {
        tab.rdpErrorMessage = getRdpConnectionErrorMessage();
      }
      finishConnectingTab(tab);
    }
  };
  client.onerror = (status) => {
    tab.status = 'error';
    tab.rdpErrorMessage = getRdpConnectionErrorMessage(status);
    finishConnectingTab(tab);
  };
  tunnel.onerror = (status) => {
    tab.status = 'error';
    tab.rdpErrorMessage = getRdpConnectionErrorMessage(status);
    finishConnectingTab(tab);
  };

  try {
    client.connect(buildRdpConnectionQuery(tab));
  } catch (error) {
    tab.status = 'error';
    tab.rdpErrorMessage = getRdpConnectionErrorMessage(error);
    finishConnectingTab(tab);
  }
}

function getRdpConnectionErrorMessage(status?: unknown) {
  return formatRdpConnectionErrorMessage(status);
}

function attachRdpInputHandlers(tab: TerminalTab, client: GuacamoleClientInstance, displayElement: HTMLElement) {
  const mouse = markRaw(new Guacamole.Mouse(displayElement));
  mouse.onEach(['mousedown', 'mousemove', 'mouseup'], (event) => {
    if (tab.status !== 'connected') return;
    client.sendMouseState((event as Guacamole.Mouse.Event).state, true);
    displayElement.focus();
  });
  mouse.on('mouseout', () => {
    client.getDisplay().showCursor(false);
  });
  tab.guacMouse = mouse;

  const keyboard = markRaw(new Guacamole.Keyboard(displayElement));
  keyboard.onkeydown = (keysym) => {
    if (tab.status !== 'connected' || tab.id !== activeTabId.value) return true;
    client.sendKeyEvent(1, keysym);
    return false;
  };
  keyboard.onkeyup = (keysym) => {
    if (tab.status !== 'connected' || tab.id !== activeTabId.value) return;
    client.sendKeyEvent(0, keysym);
  };
  tab.guacKeyboard = keyboard;
}

function handleSocketMessage(tab: TerminalTab, event: MessageEvent<string>) {
  let message: TerminalMessage;
  try {
    message = JSON.parse(event.data) as TerminalMessage;
  } catch {
    tab.terminal.writeln('\r\n\x1b[31m终端消息解析失败。\x1b[0m');
    return;
  }

  if (message.type === 'ready') {
    if (message.terminalSettings) {
      terminalSettings.value = normalizeTerminalSettings({ ...terminalSettings.value, ...message.terminalSettings });
    }
    tab.status = 'connected';
    tab.sessionId = message.sessionId ?? null;
    tab.reconnectHintShown = false;
    finishConnectingTab(tab);
    fitTerminal(tab);
    startTerminalHeartbeat(tab);
    if (tab.id === activeTabId.value) openTerminalMonitorPanel();
    return;
  }

  if (message.type === 'pong') {
    return;
  }

  if (message.type === 'output') {
    tab.terminal.write(message.data ?? '');
    if (tab.id !== activeTabId.value) {
      markTabUnread(tab.id);
    }
    return;
  }

  if (message.type === 'cwd') {
    const path = String(message.path || '').trim();
    if (!path) return;
    tab.currentCwd = path;
    return;
  }

  if (message.type === 'error') {
    if (message.message === '不支持的终端消息类型') {
      return;
    }
    if (message.message === '请先登录') {
      handleTerminalAuthExpired(new ApiUnauthorizedError(message.message));
      return;
    }
    tab.status = 'error';
    finishConnectingTab(tab);
    showTerminalReconnectHint(tab, message.message ?? '终端连接失败');
    return;
  }

  if (message.type === 'closed') {
    stopTerminalHeartbeat(tab.id);
    tab.status = 'closed';
    finishConnectingTab(tab);
    showTerminalReconnectHint(tab, message.reason ?? '连接已关闭');
  }
}

async function confirmTerminalSessionStillAuthenticated() {
  try {
    const current = await getCurrentUser();
    terminalCurrentUser.value = current.user;
  } catch (error) {
    handleTerminalAuthExpired(error);
  }
}

function getTabById(tabId: string) {
  return tabs.value.find((item) => item.id === tabId) ?? null;
}

function markTabUnread(tabId: string) {
  const tab = getTabById(tabId);
  if (tab && tab.id !== activeTabId.value && !isTerminalTabVisible(tab)) {
    tab.hasUnreadOutput = true;
  }
}

function isTerminalTabVisible(tab: TerminalTab) {
  return visibleTerminalTabs.value.some((item) => item.id === tab.id);
}

const terminalResize = useTerminalResize<TerminalTab>({
  isVisible: isTerminalTabVisible,
  fitRdp: fitRdpTerminal,
});

function fitTerminal(tab: TerminalTab) {
  terminalResize.fit(tab);
}

function startSidebarResize(event: MouseEvent, options: { alignToPointer?: boolean } = {}) {
  event.preventDefault();
  if (isTerminalSidebarCollapsed.value) setTerminalSidebarCollapsed(false);
  sidebarResizeStartX = event.clientX;
  sidebarResizeStartWidth = sidebarWidth.value;
  isResizingSidebar.value = true;
  if (options.alignToPointer) {
    sidebarWidth.value = clampTerminalSidebarWidth(event.clientX);
    sidebarResizeStartWidth = sidebarWidth.value;
  }
  window.addEventListener('mousemove', resizeSidebar);
  window.addEventListener('mouseup', stopSidebarResize);
  document.body.classList.add('terminal-resizing');
}

function resizeSidebar(event: MouseEvent) {
  if (!isResizingSidebar.value) return;
  const nextWidth = clampTerminalSidebarWidth(sidebarResizeStartWidth + event.clientX - sidebarResizeStartX);
  sidebarWidth.value = nextWidth;
  window.localStorage.setItem(TERMINAL_SIDEBAR_WIDTH_STORAGE_KEY, String(nextWidth));
  fitActiveTerminalSoon();
}

function clampTerminalSidebarWidth(width: number) {
  const viewportWidth = typeof window === 'undefined' ? 0 : window.innerWidth;
  const maxWidth = Math.max(
    TERMINAL_SIDEBAR_MIN_WIDTH,
    viewportWidth - TERMINAL_WORKSPACE_MIN_WIDTH,
  );
  return Math.min(Math.max(width, TERMINAL_SIDEBAR_MIN_WIDTH), maxWidth);
}

function syncTerminalSidebarWidth() {
  if (isTerminalSidebarCollapsed.value) {
    fitActiveTerminalSoon();
    return;
  }
  const nextWidth = clampTerminalSidebarWidth(sidebarWidth.value);
  if (nextWidth !== sidebarWidth.value) {
    sidebarWidth.value = nextWidth;
    window.localStorage.setItem(TERMINAL_SIDEBAR_WIDTH_STORAGE_KEY, String(nextWidth));
  }
  fitActiveTerminalSoon();
}

function stopSidebarResize() {
  if (!isResizingSidebar.value) return;
  isResizingSidebar.value = false;
  window.removeEventListener('mousemove', resizeSidebar);
  window.removeEventListener('mouseup', stopSidebarResize);
  document.body.classList.remove('terminal-resizing');
  fitActiveTerminalSoon();
}

function selectTerminalSidebarMode(mode: TerminalSidebarMode) {
  if ((mode === 'files' || mode === 'commands') && !activeTerminalSupportsSshTools.value) {
    terminalSidebarMode.value = 'hosts';
    return;
  }
  if (mode === 'commands' && !shouldShowTerminalQuickCommandPanel.value) return;
  terminalSidebarMode.value = mode;
  if (mode === 'commands' && isTerminalQuickCommandPanelCollapsed.value) {
    toggleTerminalQuickCommandPanel();
  }
  if (mode === 'commands') {
    setTerminalSidebarCollapsed(true);
    return;
  }
  if (isTerminalSidebarCollapsed.value) setTerminalSidebarCollapsed(false);
}

function toggleTerminalQuickCommandFromRail() {
  if (!shouldShowTerminalQuickCommandPanel.value) return;
  toggleTerminalQuickCommandPanel();
}

function openTerminalMonitorPanel() {
  if (!activeTerminalSupportsSshTools.value) return;
  if (isTerminalMonitorPanelOpen.value) {
    syncTerminalMonitorPolling();
    fitActiveTerminalSoon();
    return;
  }
  isTerminalMonitorPanelOpen.value = true;
}

function closeTerminalMonitorPanel() {
  if (!isTerminalMonitorPanelOpen.value) return;
  isTerminalMonitorPanelOpen.value = false;
}

function toggleTerminalMonitorPanel() {
  if (!activeTerminalSupportsSshTools.value) return;
  if (isTerminalMonitorPanelOpen.value) {
    closeTerminalMonitorPanel();
  } else {
    openTerminalMonitorPanel();
  }
}

function fitRdpTerminal(tab: TerminalTab) {
  const client = tab.guacClient;
  const container = terminalContainers.get(tab.id);
  if (!client || !container) return;
  const width = Math.max(320, Math.floor(container.clientWidth || 1280));
  const height = Math.max(240, Math.floor(container.clientHeight || 720));
  try {
    const display = client.getDisplay();
    client.sendSize(width, height);
    const scale = calculateRdpDisplayScale(width, height, display.getWidth(), display.getHeight());
    if (scale !== null) display.scale(scale);
  } catch {
    // The Guacamole display may not be ready until the RDP handshake completes.
  }
}

async function toggleRdpFullscreen(tab: TerminalTab | null) {
  if (!tab || tab.kind !== 'rdp') return;
  const container = terminalContainers.get(tab.id);
  if (!container) return;
  try {
    if (document.fullscreenElement === container) {
      await document.exitFullscreen();
    } else {
      await container.requestFullscreen();
      tab.guacDisplayElement?.focus();
    }
  } catch {
    // Browser fullscreen can be blocked outside a trusted user gesture.
  } finally {
    fitTerminal(tab);
  }
}

function toggleTerminalSidebar() {
  setTerminalSidebarCollapsed(!isTerminalSidebarCollapsed.value);
}

function setTerminalSidebarCollapsed(collapsed: boolean) {
  isTerminalSidebarCollapsed.value = collapsed;
  window.localStorage.setItem(TERMINAL_SIDEBAR_COLLAPSED_STORAGE_KEY, collapsed ? '1' : '0');
  if (collapsed) stopSidebarResize();
  closeTerminalContextMenus();
  fitActiveTerminalSoon();
}

function fitActiveTerminalSoon() {
  fitVisibleTerminalsSoon();
}

function fitVisibleTerminalsSoon() {
  window.requestAnimationFrame(() => {
    for (const tab of visibleTerminalTabs.value) fitTerminal(tab);
  });
}

function setTerminalFontSize(nextSize: number) {
  const normalized = clampTerminalFontSize(nextSize);
  if (normalized === terminalFontSize.value) return;
  terminalFontSize.value = normalized;
  window.localStorage.setItem(TERMINAL_FONT_SIZE_STORAGE_KEY, String(normalized));
  for (const tab of tabs.value) {
    if (tab.kind === 'ssh') {
      tab.terminal.options.fontSize = normalized;
    }
  }
  fitActiveTerminalSoon();
}

function decreaseTerminalFontSize() {
  setTerminalFontSize(terminalFontSize.value - 1);
}

function increaseTerminalFontSize() {
  setTerminalFontSize(terminalFontSize.value + 1);
}

async function closeTab(tab: TerminalTab) {
  closeTerminalTabMenu();
  closeTerminalTabContextMenu();
  await closeTerminalTabs([tab]);
}

async function closeTerminalTabs(targetTabs: TerminalTab[]) {
  const { nextActiveId, closedTabs } = removeTerminalTabs(targetTabs);
  if (!closedTabs.length) return;

  for (const tab of closedTabs) terminalContainers.delete(tab.id);
  pruneTerminalMultiExecutionExclusions();
  await nextTick();

  if (nextActiveId) await activateTab(nextActiveId);
  if (!activeTabId.value) closeTerminalMonitorPanel();
  saveTerminalWorkspace();
  syncTerminalTabsScrollStateSoon();
}

async function restoreTerminalWorkspace() {
  const workspace = loadTerminalWorkspace();
  if (!workspace?.tabs.length || treeError.value) return;

  const restoredTabs = workspace.tabs
    .map((item) => {
      const host = findHostById(groups.value, item.hostId);
      return host ? createTerminalTab(host, item.id, { customTitle: item.title, colorId: item.colorId ?? null }) : null;
    })
    .filter((tab): tab is TerminalTab => Boolean(tab));

  if (!restoredTabs.length) {
    saveTerminalWorkspace();
    return;
  }

  replaceTerminalTabs(restoredTabs, workspace.activeTabId);
  saveTerminalWorkspace();

  await nextTick();
  scrollActiveTerminalTabIntoView();
  for (const tab of restoredTabs) {
    mountTerminal(tab);
    enqueueConnectTab(tab);
  }
}

function loadTerminalWorkspace(): PersistedTerminalWorkspace | null {
  if (typeof window === 'undefined') return null;

  const raw = window.sessionStorage.getItem(TERMINAL_WORKSPACE_STORAGE_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<PersistedTerminalWorkspace>;
    if (!Array.isArray(parsed.tabs)) return null;

    const seenIds = new Set<string>();
    const persistedTabs = parsed.tabs.flatMap((item) => {
      if (!item || typeof item !== 'object') return [];
      const id = typeof item.id === 'string' && item.id ? item.id : '';
      const hostId = Number(item.hostId);
      if (!id || !Number.isFinite(hostId) || seenIds.has(id)) return [];
      seenIds.add(id);
      const title = normalizeTerminalTabTitle((item as Partial<PersistedTerminalTab>).title);
      const colorId = normalizeTerminalTabColorId((item as Partial<PersistedTerminalTab>).colorId);
      return [{
        id,
        hostId,
        ...(title ? { title } : {}),
        ...(colorId ? { colorId } : {}),
      }];
    });

    return {
      tabs: persistedTabs,
      activeTabId: typeof parsed.activeTabId === 'string' ? parsed.activeTabId : null,
    };
  } catch {
    return null;
  }
}

function saveTerminalWorkspace() {
  if (typeof window === 'undefined') return;

  const workspace: PersistedTerminalWorkspace = {
    tabs: tabs.value.map((tab) => ({
      id: tab.id,
      hostId: tab.host.id,
      ...(tab.customTitle ? { title: tab.customTitle } : {}),
      ...(tab.colorId ? { colorId: tab.colorId } : {}),
    })),
    activeTabId: activeTabId.value,
  };

  if (!workspace.tabs.length) {
    window.sessionStorage.removeItem(TERMINAL_WORKSPACE_STORAGE_KEY);
    return;
  }

  window.sessionStorage.setItem(TERMINAL_WORKSPACE_STORAGE_KEY, JSON.stringify(workspace));
}

function disposeTab(tab: TerminalTab) {
  tab.status = 'closed';
  stopTerminalHeartbeat(tab.id);
  removePendingConnectTab(tab.id);
  finishConnectingTab(tab);
  sshTerminal.disconnect(tab);
  cleanupRdpClient(tab);
  terminalResize.dispose(tab.id);
  for (const disposable of tab.disposables) disposable.dispose();
  tab.disposables = [];
  tab.terminal.dispose();
}

function removePendingConnectTab(tabId: string) {
  const index = pendingConnectTabIds.indexOf(tabId);
  if (index !== -1) {
    pendingConnectTabIds.splice(index, 1);
  }
}

function setTerminalContainer(tabId: string, element: unknown) {
  if (element instanceof HTMLElement) {
    terminalContainers.set(tabId, element);
    const tab = tabs.value.find((item) => item.id === tabId);
    if (tab) mountTerminal(tab);
  } else {
    terminalContainers.delete(tabId);
  }
}

function buildWebSocketUrl(hostId: number) {
  return buildTerminalWebSocketUrl(window.location.protocol, window.location.host, hostId);
}

function buildRdpWebSocketUrl(tab: TerminalTab) {
  return buildRdpWebSocketUrlValue(window.location.protocol, window.location.host, tab.host.id);
}

function buildRdpConnectionQuery(tab: TerminalTab) {
  const container = terminalContainers.get(tab.id);
  return buildRdpConnectionQueryValue(container?.clientWidth, container?.clientHeight);
}

function cleanupRdpClient(tab: TerminalTab) {
  if (tab.guacKeyboard) {
    tab.guacKeyboard.onkeydown = null;
    tab.guacKeyboard.onkeyup = null;
  }
  try {
    const display = tab.guacClient?.getDisplay();
    if (display) display.onresize = null;
  } catch {
    // The display may already be torn down during reconnect races.
  }
  try {
    tab.guacClient?.disconnect();
  } catch {
    // Ignore disconnect races while closing or reconnecting a tab.
  }
  tab.guacClient = null;
  tab.guacTunnel = null;
  tab.guacMouse = null;
  tab.guacKeyboard = null;
  tab.guacDisplayElement?.remove();
  tab.guacDisplayElement = null;
}

function highlightTerminalOutput(output: string, state: TerminalHighlightState) {
  if (!output && !state.pendingControl) return '';

  const source = state.pendingControl + output;
  state.pendingControl = getTrailingAnsiPrefix(source);
  const parseableOutput = state.pendingControl ? source.slice(0, -state.pendingControl.length) : source;
  const shouldHighlight = highlightEnabled.value;

  let result = '';
  let lastIndex = 0;
  ANSI_CONTROL_PATTERN.lastIndex = 0;

  for (let match = ANSI_CONTROL_PATTERN.exec(parseableOutput); match; match = ANSI_CONTROL_PATTERN.exec(parseableOutput)) {
    if (match.index > lastIndex) {
      const plainText = parseableOutput.slice(lastIndex, match.index);
      result += shouldHighlight && !state.sgrActive ? highlightPlainText(plainText) : plainText;
    }

    const controlSequence = match[0];
    result += controlSequence;
    state.sgrActive = getNextSgrState(controlSequence, state.sgrActive);
    lastIndex = match.index + controlSequence.length;
  }

  if (lastIndex < parseableOutput.length) {
    const plainText = parseableOutput.slice(lastIndex);
    result += shouldHighlight && !state.sgrActive ? highlightPlainText(plainText) : plainText;
  }

  return result;
}

function getTrailingAnsiPrefix(output: string) {
  const escapeIndex = output.lastIndexOf('\x1b');
  if (escapeIndex === -1) return '';

  const suffix = output.slice(escapeIndex);
  if (suffix.startsWith('\x1b]')) {
    const bellIndex = suffix.indexOf('\x07', 2);
    const stringTerminatorIndex = suffix.indexOf('\x1b\\', 2);
    return bellIndex === -1 && stringTerminatorIndex === -1 ? suffix : '';
  }

  return ANSI_CONTROL_PREFIX_PATTERN.test(suffix) ? suffix : '';
}

function highlightPlainText(text: string) {
  const matches: Array<{ start: number; end: number; rule: TerminalHighlightRule; priority: number }> = [];

  terminalHighlightRules.forEach((rule, priority) => {
    rule.pattern.lastIndex = 0;
    for (let match = rule.pattern.exec(text); match; match = rule.pattern.exec(text)) {
      if (!match[0]) {
        rule.pattern.lastIndex += 1;
        continue;
      }
      matches.push({ start: match.index, end: match.index + match[0].length, rule, priority });
    }
  });

  if (!matches.length) return text;

  matches.sort((left, right) => left.start - right.start || left.priority - right.priority || right.end - left.end);

  let result = '';
  let cursor = 0;
  for (const match of matches) {
    if (match.start < cursor) continue;
    result += text.slice(cursor, match.start);
    result += `${match.rule.open}${text.slice(match.start, match.end)}${match.rule.close}`;
    cursor = match.end;
  }
  result += text.slice(cursor);

  return result;
}

function getNextSgrState(sequence: string, current: boolean) {
  if (!sequence.endsWith('m')) return current;

  const rawParams = sequence.slice(2, -1);
  const params = rawParams ? rawParams.split(';') : ['0'];
  if (params.some((param) => param === '' || param === '0')) return false;

  return true;
}

function flattenTerminalRows(source: TerminalGroup[], hidden: Set<number>, level = 0): TreeRow[] {
  return source.flatMap((group) => {
    const current: TreeRow[] = [{ kind: 'group', group, level }];
    if (!hidden.has(group.id)) {
      current.push(...flattenTerminalRows(group.children, hidden, level + 1));
      current.push(...group.hosts.map((host) => ({ kind: 'host' as const, host, level: level + 1 })));
    }
    return current;
  });
}

function countTerminalHosts(source: TerminalGroup[]): number {
  return source.reduce((total, group) => total + group.hosts.length + countTerminalHosts(group.children), 0);
}

function findHostById(source: TerminalGroup[], hostId: number): TerminalHost | null {
  for (const group of source) {
    const host = group.hosts.find((item) => item.id === hostId);
    if (host) return host;
    const childHost = findHostById(group.children, hostId);
    if (childHost) return childHost;
  }
  return null;
}

function readTerminalRootLabel() {
  if (typeof window === 'undefined') return 'DEFAULT';
  return window.localStorage.getItem('ops-tool.host-manager.root-label') || 'DEFAULT';
}

function readTerminalSidebarWidth() {
  if (typeof window === 'undefined') return TERMINAL_SIDEBAR_DEFAULT_WIDTH;
  const saved = Number(window.localStorage.getItem(TERMINAL_SIDEBAR_WIDTH_STORAGE_KEY));
  if (!Number.isFinite(saved)) return TERMINAL_SIDEBAR_DEFAULT_WIDTH;
  return clampTerminalSidebarWidth(saved);
}

function readTerminalSidebarCollapsed() {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(TERMINAL_SIDEBAR_COLLAPSED_STORAGE_KEY) === '1';
}

function readTerminalFontSize() {
  if (typeof window === 'undefined') return TERMINAL_FONT_SIZE_DEFAULT;
  return readStoredTerminalFontSize(window.localStorage.getItem(TERMINAL_FONT_SIZE_STORAGE_KEY), terminalSettings.value.defaultFontSize);
}

function readTerminalSplitMode(): TerminalSplitMode {
  if (typeof window === 'undefined') return 'single';
  const saved = window.localStorage.getItem(TERMINAL_SPLIT_MODE_STORAGE_KEY);
  return saved === 'auto' || saved === 'horizontal' || saved === 'vertical' ? saved : 'single';
}

function readTerminalQuickCommandPanelHeight() {
  if (typeof window === 'undefined') return TERMINAL_QUICK_COMMAND_PANEL_DEFAULT_HEIGHT;
  const saved = Number(window.localStorage.getItem(TERMINAL_QUICK_COMMAND_PANEL_HEIGHT_STORAGE_KEY));
  if (!Number.isFinite(saved)) return TERMINAL_QUICK_COMMAND_PANEL_DEFAULT_HEIGHT;
  return clampTerminalQuickCommandPanelHeight(saved);
}

function readTerminalQuickCommandPanelCollapsed() {
  if (typeof window === 'undefined') return false;
  return window.localStorage.getItem(TERMINAL_QUICK_COMMAND_PANEL_COLLAPSED_STORAGE_KEY) === '1';
}
</script>

<template>
  <main class="terminal-shell" :class="{ resizing: isResizingSidebar, 'sidebar-collapsed': isTerminalSidebarCollapsed }" :style="terminalShellStyle">
    <aside class="terminal-sidebar">
      <nav class="terminal-side-switch" aria-label="终端侧栏切换" @mousedown.self="startSidebarResize" @dblclick.stop="toggleTerminalSidebar">
        <el-button
          native-type="button"
          title="服务器列表"
          aria-label="服务器列表"
          :class="{ active: terminalSidebarMode === 'hosts' }"
          @click="selectTerminalSidebarMode('hosts')"
        >
          <AppIcon name="server" :size="18" />
        </el-button>
        <el-button
          native-type="button"
          title="FTP 文件夹"
          aria-label="FTP 文件夹"
          :class="{ active: terminalSidebarMode === 'files' }"
          :disabled="!activeTerminalSupportsSshTools"
          @click="selectTerminalSidebarMode('files')"
        >
          <AppIcon name="folder" :size="19" />
        </el-button>
        <el-button
          native-type="button"
          :title="isTerminalMonitorPanelOpen ? '关闭资源监控' : '打开资源监控'"
          :aria-label="isTerminalMonitorPanelOpen ? '关闭资源监控' : '打开资源监控'"
          :aria-pressed="isTerminalMonitorPanelOpen"
          :class="{ active: isTerminalMonitorPanelOpen }"
          :disabled="!activeTerminalSupportsSshTools"
          @click="toggleTerminalMonitorPanel"
        >
          <AppIcon name="monitor" :size="18" />
        </el-button>
        <el-button
          class="terminal-sidebar-collapse-button"
          native-type="button"
          :title="terminalSidebarToggleLabel"
          :aria-label="terminalSidebarToggleLabel"
          :aria-pressed="isTerminalSidebarCollapsed"
          @click="toggleTerminalSidebar"
        >
          <AppIcon name="chevronsRight" :size="17" />
        </el-button>
        <el-button
          v-if="shouldShowTerminalQuickCommandPanel"
          class="terminal-quick-toggle-button"
          native-type="button"
          title="打开/关闭快捷命令"
          aria-label="打开/关闭快捷命令"
          :aria-pressed="!isTerminalQuickCommandPanelCollapsed"
          :class="{ active: !isTerminalQuickCommandPanelCollapsed }"
          @click.stop="toggleTerminalQuickCommandFromRail"
          @dblclick.stop
        >
          <AppIcon name="zap" :size="18" />
        </el-button>
      </nav>
      <div class="terminal-sidebar-panel">
        <template v-if="terminalSidebarMode === 'hosts'">
          <div class="terminal-search">
            <el-input v-model="search" placeholder="输入主机名/IP检索" clearable />
            <el-button native-type="button" title="刷新" aria-label="刷新" @click="loadTree"><AppIcon name="refresh" :size="16" /></el-button>
          </div>
          <div class="terminal-tree">
            <el-button
              v-for="row in rows"
              :key="row.kind === 'root' ? 'group-root' : row.kind === 'group' ? `group-${row.group.id}` : `host-${row.host.id}`"
              class="terminal-tree-row"
              :class="{ root: row.kind === 'root', host: row.kind === 'host', active: row.kind === 'host' && activeTab?.host.id === row.host.id }"
              :style="{ paddingLeft: `${12 + row.level * 24}px` }"
              :title="row.kind === 'host' ? getTerminalHostTooltip(row.host) : undefined"
              native-type="button"
              @click="row.kind === 'root' ? toggleRoot() : row.kind === 'group' && toggleGroup(row.group)"
              @dblclick="row.kind === 'host' && openHostTab(row.host)"
            >
              <template v-if="row.kind === 'root'">
                <span><AppIcon :name="rootExpanded ? 'chevronDown' : 'chevronRight'" :size="15" /></span>
                <strong><AppIcon name="folder" :size="16" />{{ row.group.name }}</strong>
                <em>{{ row.group.count }}</em>
              </template>
              <template v-else-if="row.kind === 'group'">
                <span><AppIcon :name="collapsed.has(row.group.id) ? 'chevronRight' : 'chevronDown'" :size="15" /></span>
                <strong><AppIcon name="folder" :size="16" />{{ row.group.name }}</strong>
              </template>
              <template v-else>
                <span><AppIcon name="server" :size="15" /></span>
                <strong>{{ row.host.name }}</strong>
                <i
                  v-if="row.host.verified || row.host.verifyStatus === 'failed'"
                  class="terminal-host-verify-dot"
                  :class="{ failed: row.host.verifyStatus === 'failed' }"
                  :title="row.host.verifyStatus === 'failed' ? '验证失败' : '已验证'"
                  :aria-label="row.host.verifyStatus === 'failed' ? '验证失败' : '已验证'"
                ></i>
              </template>
            </el-button>
            <p v-if="isLoadingTree" class="terminal-tree-empty">加载中...</p>
            <p v-else-if="treeError" class="terminal-tree-empty">{{ treeError }}</p>
            <p v-else-if="!rows.length" class="terminal-tree-empty">没有匹配的主机。</p>
          </div>
        </template>
        <SftpPanel
          :visible="terminalSidebarMode === 'files'"
          :active="activeTerminalSupportsSshTools"
          :session-key="activeTab?.id ?? null"
          :host-id="activeTab?.host.id ?? null"
          :current-cwd="activeTab?.currentCwd ?? ''"
          :node-name="activeTerminalNodeName"
          :handle-unauthorized="handleTerminalAuthExpired"
          @write-terminal="writeTerminalTextFromSftp"
        />
      </div>
    </aside>
    <div
      class="terminal-sidebar-resizer"
      role="separator"
      aria-label="调整主机列表宽度"
      aria-orientation="vertical"
      @mousedown="startSidebarResize($event, { alignToPointer: true })"
    ></div>

    <section
      class="terminal-workspace"
      :class="{
        'quick-panel-collapsed': shouldShowTerminalQuickCommandPanel && isTerminalQuickCommandPanelCollapsed,
        'quick-panel-resizing': shouldShowTerminalQuickCommandPanel && isTerminalQuickCommandPanelResizing,
        'multi-execution-enabled': isTerminalMultiExecutionEnabled,
      }"
      :style="terminalQuickCommandPanelStyle"
    >
      <div class="terminal-hint">
        <div class="terminal-hint-actions">
          <el-button
            native-type="button"
            class="terminal-multi-execution-toggle"
            :class="{ active: isTerminalMultiExecutionEnabled }"
            :title="isTerminalMultiExecutionEnabled ? '退出多执行模式' : '开启多执行模式'"
            :aria-label="isTerminalMultiExecutionEnabled ? '退出多执行模式' : '开启多执行模式'"
            :aria-pressed="isTerminalMultiExecutionEnabled"
            :disabled="!activeTerminalSupportsSshTools || (!isTerminalMultiExecutionEnabled && !hasTerminalMultiExecutionCandidates)"
            @click="toggleTerminalMultiExecution"
          >
            <AppIcon name="chevronsRight" :size="15" />
          </el-button>
          <div class="terminal-split-menu" @click.stop>
            <el-button
              native-type="button"
              class="terminal-split-trigger"
              :class="{ active: isTerminalSplitMenuOpen || terminalSplitMode !== 'single' }"
              :title="`分屏布局：${terminalSplitModeLabel}`"
              :aria-label="`分屏布局：${terminalSplitModeLabel}`"
              :aria-expanded="isTerminalSplitMenuOpen"
              @click="toggleTerminalSplitMenu"
            >
              <AppIcon name="dashboard" :size="15" />
            </el-button>
            <div v-if="isTerminalSplitMenuOpen" class="terminal-split-menu-list" role="menu" aria-label="分屏布局">
              <el-button
                v-for="option in terminalSplitModeOptions"
                :key="option.mode"
                native-type="button"
                class="terminal-split-menu-item"
                :class="{ active: terminalSplitMode === option.mode }"
                role="menuitem"
                @click="setTerminalSplitMode(option.mode)"
              >
                <AppIcon :name="option.icon" :size="15" />
                <span>{{ option.label }}</span>
                <AppIcon v-if="terminalSplitMode === option.mode" name="check" :size="14" />
              </el-button>
            </div>
          </div>
          <el-button
            native-type="button"
            class="terminal-highlight-toggle"
            :class="{ active: highlightEnabled }"
            :title="highlightEnabled ? '关闭关键词高亮' : '开启关键词高亮'"
            :aria-label="highlightEnabled ? '关闭关键词高亮' : '开启关键词高亮'"
            :aria-pressed="highlightEnabled"
            :disabled="!activeTerminalSupportsSshTools"
            @click="highlightEnabled = !highlightEnabled"
          >
            <AppIcon name="sun" :size="15" />
          </el-button>
          <div class="terminal-font-controls" :title="`终端字号 ${terminalFontSize}px`" aria-label="终端字号">
            <el-button
              native-type="button"
              title="缩小终端字体"
              aria-label="缩小终端字体"
              :disabled="!activeTerminalSupportsSshTools || !canDecreaseTerminalFontSize"
              @click="decreaseTerminalFontSize"
            >
              <AppIcon name="zoomOut" :size="15" />
            </el-button>
            <span>{{ terminalFontSize }}</span>
            <el-button
              native-type="button"
              title="放大终端字体"
              aria-label="放大终端字体"
              :disabled="!activeTerminalSupportsSshTools || !canIncreaseTerminalFontSize"
              @click="increaseTerminalFontSize"
            >
              <AppIcon name="zoomIn" :size="15" />
            </el-button>
          </div>
          <el-button
            native-type="button"
            class="terminal-search-toggle"
            :class="{ active: isTerminalSearchOpen }"
            title="查找当前终端"
            aria-label="查找当前终端"
            :aria-pressed="isTerminalSearchOpen"
            :disabled="!activeTerminalSupportsSshTools"
            @click="openTerminalSearch()"
          >
            <AppIcon name="search" :size="15" />
          </el-button>
          <el-button
            v-if="activeTab?.kind === 'rdp'"
            native-type="button"
            class="terminal-search-toggle"
            title="全屏远程桌面"
            aria-label="全屏远程桌面"
            @click="toggleRdpFullscreen(activeTab)"
          >
            <AppIcon name="maximize" :size="15" />
          </el-button>
        </div>
        <span class="terminal-workspace-title">{{ workspaceTitle }}</span>
      </div>
      <div v-if="isTerminalMultiExecutionEnabled" class="terminal-multi-execution-bar">
        <div class="terminal-multi-execution-info">
          <AppIcon name="chevronsRight" :size="16" />
          <strong>多执行模式</strong>
          <span>{{ getTerminalMultiExecutionStatusText() }}</span>
        </div>
        <div class="terminal-multi-execution-actions">
          <el-button
            native-type="button"
            title="多粘贴"
            aria-label="多粘贴"
            :disabled="!canSendToTerminalMultiExecutionTargets"
            @click="pasteClipboardToTerminalMultiExecutionTargets"
          >
            <AppIcon name="clipboard" :size="14" />
            <span>多粘贴</span>
          </el-button>
          <el-button native-type="button" title="退出多执行模式" aria-label="退出多执行模式" @click="exitTerminalMultiExecution">
            <AppIcon name="x" :size="14" />
            <span>退出</span>
          </el-button>
        </div>
      </div>
      <div class="terminal-tabbar">
        <AppContextMenu
          :open="terminalTabContextMenu.visible"
          :items="terminalTabContextMenuItems"
          :disabled="!tabs.length"
          @update:open="!$event && closeTerminalTabContextMenu()"
          @select="runTerminalTabContextMenuItem"
        >
          <div ref="terminalTabsRef" class="terminal-tabs" @scroll="syncTerminalTabsScrollState">
            <el-button
              v-for="tab in tabs"
              :key="tab.id"
              native-type="button"
              class="terminal-tab"
              :data-terminal-tab-id="tab.id"
              :class="{
                active: tab.id === activeTabId,
                closed: tab.status === 'closed',
                error: tab.status === 'error',
                'multi-execution-target': shouldShowTerminalMultiExecutionTabIndicator(tab),
              }"
              :style="getTerminalTabStyle(tab)"
              @click="activateTab(tab.id)"
              @contextmenu="openTerminalTabContextMenu(tab, $event)"
            >
              <span class="terminal-tab-label">{{ getTerminalTabLabel(tab) }}</span>
              <span
                v-if="shouldShowTerminalMultiExecutionTabIndicator(tab)"
                class="terminal-tab-multi-execution-indicator"
                title="多执行控制中"
                aria-label="多执行控制中"
              >
                <AppIcon name="chevronsRight" :size="12" :stroke-width="2.5" />
              </span>
              <span class="terminal-tab-status" :class="[tab.status, { unread: tab.hasUnreadOutput && tab.id !== activeTabId }]"></span>
              <span class="terminal-tab-close" title="关闭" @click.stop="closeTab(tab)"><AppIcon name="x" :size="13" /></span>
            </el-button>
          </div>
        </AppContextMenu>
        <div v-if="tabs.length" class="terminal-tab-overview" @click.stop>
          <el-button
            native-type="button"
            class="terminal-tab-scroll-button previous"
            title="向左移动标签"
            aria-label="向左移动标签"
            :disabled="!canScrollTerminalTabsLeft"
            @click="scrollTerminalTabs('left')"
          >
            <AppIcon name="chevronRight" :size="15" />
          </el-button>
          <el-button
            native-type="button"
            class="terminal-tab-scroll-button next"
            title="向右移动标签"
            aria-label="向右移动标签"
            :disabled="!canScrollTerminalTabsRight"
            @click="scrollTerminalTabs('right')"
          >
            <AppIcon name="chevronRight" :size="15" />
          </el-button>
          <el-button
            native-type="button"
            class="terminal-tab-menu-trigger"
            :class="{ active: isTerminalTabMenuOpen }"
            title="打开的标签"
            aria-label="打开的标签"
            :aria-expanded="isTerminalTabMenuOpen"
            @click="toggleTerminalTabMenu"
          >
            <AppIcon name="link" :size="16" />
          </el-button>
          <div v-if="isTerminalTabMenuOpen" class="terminal-tab-menu" role="menu" aria-label="打开的标签">
            <header>打开的标签</header>
            <el-button
              v-for="(tab, index) in tabs"
              :key="`menu-${tab.id}`"
              native-type="button"
              class="terminal-tab-menu-item"
              :class="{ active: tab.id === activeTabId, closed: tab.status === 'closed', error: tab.status === 'error' }"
              role="menuitem"
              @click="selectTerminalTabFromMenu(tab)"
            >
              <span class="terminal-tab-menu-check">
                <AppIcon v-if="tab.id === activeTabId" name="check" :size="15" />
              </span>
              <AppIcon name="server" :size="15" />
              <span class="terminal-tab-menu-label">{{ index + 1 }} {{ getTerminalTabLabel(tab) }}</span>
              <span class="terminal-tab-status" :class="[tab.status, { unread: tab.hasUnreadOutput && tab.id !== activeTabId }]"></span>
            </el-button>
          </div>
        </div>
      </div>
      <div class="terminal-workspace-body" :class="{ 'monitor-open': isTerminalMonitorPanelOpen }">
        <AppContextMenu
          :open="terminalContextMenu.visible"
          :items="terminalContextMenuItems"
          :disabled="!tabs.length"
          @update:open="!$event && closeTerminalContextMenu()"
          @select="runTerminalContextMenuItem"
        >
          <div
            class="terminal-screen"
            :class="[`split-${terminalSplitMode}`, { 'split-active': isTerminalSplitActive }]"
            :style="terminalScreenStyle"
          >
            <div v-if="!tabs.length" class="terminal-empty">双击左侧主机名连接 SSH 终端。</div>
            <div
              v-for="tab in tabs"
              :key="tab.id"
              class="terminal-panel"
              :class="{
                active: tab.id === activeTabId,
                visible: isTerminalTabVisible(tab),
                excluded: isTerminalMultiExecutionEnabled && isTerminalMultiExecutionExcluded(tab),
              }"
              :aria-hidden="!isTerminalTabVisible(tab)"
              @mousedown.capture="isTerminalTabVisible(tab) && tab.id !== activeTabId && activateTab(tab.id)"
              @contextmenu="openTerminalContextMenu(tab, $event)"
            >
              <div
                v-if="isTerminalSearchOpen && tab.id === activeTabId"
                class="terminal-panel-search"
                @click.stop
                @mousedown.stop
                @contextmenu.stop
              >
                <AppIcon name="search" :size="14" />
                <el-input
                  ref="terminalSearchInputRef"
                  v-model="terminalSearchQuery"
                  type="search"
                  placeholder="查找当前终端"
                  @keydown.enter.prevent="searchCurrentTerminal($event.shiftKey ? 'previous' : 'next')"
                  @keydown.esc.prevent.stop="closeTerminalSearch"
                />
                <span class="terminal-panel-search-count">{{ terminalSearchResultText }}</span>
                <el-button native-type="button" title="上一个" aria-label="上一个" :disabled="!terminalSearchQuery.trim()" @click="searchCurrentTerminal('previous')">
                  <AppIcon name="chevronDown" :size="14" />
                </el-button>
                <el-button native-type="button" title="下一个" aria-label="下一个" :disabled="!terminalSearchQuery.trim()" @click="searchCurrentTerminal('next')">
                  <AppIcon name="chevronDown" :size="14" />
                </el-button>
                <el-button native-type="button" title="关闭" aria-label="关闭" @click="closeTerminalSearch">
                  <AppIcon name="x" :size="14" />
                </el-button>
              </div>
              <div
                :ref="(element) => setTerminalContainer(tab.id, element)"
                :class="tab.kind === 'rdp' ? 'terminal-rdp-host' : 'terminal-xterm-host'"
              ></div>
              <div v-if="tab.kind === 'rdp' && tab.rdpErrorMessage" class="terminal-rdp-status-overlay">
                <strong>RDP connection failed</strong>
                <span>{{ tab.rdpErrorMessage }}</span>
              </div>
              <label
                v-if="isTerminalMultiExecutionEnabled && tab.kind === 'ssh'"
                class="terminal-multi-execution-exclude"
                @click.stop
                @mousedown.stop
                @contextmenu.stop
              >
                <el-checkbox
                  :model-value="isTerminalMultiExecutionExcluded(tab)"
                  @change="setTerminalMultiExecutionExcludedFromEvent(tab, $event)"
                />
                <span>不控制 {{ getTerminalTabLabel(tab) }}</span>
              </label>
            </div>
          </div>
        </AppContextMenu>
        <div
          v-if="terminalPastePrompt.visible"
          class="terminal-paste-prompt"
          :style="{ left: `${terminalPastePrompt.x}px`, top: `${terminalPastePrompt.y}px` }"
          @click.stop
          @contextmenu.stop
        >
          <span>在此粘贴后自动发送到终端</span>
          <el-input
            ref="terminalPasteInputRef"
            v-model="terminalPastePrompt.value"
            type="textarea"
            placeholder="按 Ctrl+V，或右键选择粘贴"
            @paste="handleTerminalPastePromptPaste"
            @keydown.esc.prevent.stop="closeTerminalPastePrompt"
            @keydown.ctrl.enter.prevent="submitTerminalPastePrompt()"
          />
          <div>
            <el-button native-type="button" @click="submitTerminalPastePrompt()">发送</el-button>
            <el-button native-type="button" @click="closeTerminalPastePrompt">取消</el-button>
          </div>
        </div>
        <aside v-if="isTerminalMonitorPanelOpen" class="terminal-monitor-panel terminal-monitor-drawer">
          <header class="terminal-monitor-title">
            <strong>资源监控</strong>
            <span>{{ terminalMonitorNodeName }}</span>
            <div class="terminal-monitor-actions">
              <el-button
                class="terminal-monitor-refresh"
                native-type="button"
                title="刷新"
                aria-label="刷新"
                :disabled="!activeTab || isTerminalMonitorLoading"
                @click="loadTerminalMonitor"
              >
                <AppIcon name="refresh" :size="15" />
              </el-button>
              <el-button
                class="terminal-monitor-refresh"
                native-type="button"
                title="关闭资源监控"
                aria-label="关闭资源监控"
                @click="closeTerminalMonitorPanel"
              >
                <AppIcon name="x" :size="15" />
              </el-button>
            </div>
          </header>

          <div v-if="!activeTab" class="terminal-monitor-empty">请选择服务器</div>
          <div v-else class="terminal-monitor-body">
            <p v-if="terminalMonitorError" class="terminal-monitor-error">{{ terminalMonitorError }}</p>

            <template v-if="terminalMonitorData">
              <section class="terminal-monitor-card terminal-monitor-system">
                <h3><AppIcon name="monitor" :size="15" />系统</h3>
                <dl>
                  <div>
                    <dt>主机名称</dt>
                    <dd>{{ terminalMonitorData.system.hostname }}</dd>
                  </div>
                  <div>
                    <dt>系统架构</dt>
                    <dd>{{ terminalMonitorData.system.arch }}</dd>
                  </div>
                  <div>
                    <dt>操作系统</dt>
                    <dd>{{ terminalMonitorData.system.os }}</dd>
                  </div>
                  <div>
                    <dt>运行时长</dt>
                    <dd>{{ formatMonitorUptime(terminalMonitorData.system.uptimeSeconds) }}</dd>
                  </div>
                </dl>
              </section>

              <section class="terminal-monitor-card">
                <h3><AppIcon name="cpu" :size="15" />CPU</h3>
                <div class="terminal-monitor-usage">
                  <div class="terminal-monitor-ring" :style="monitorProgressStyle(terminalMonitorData.cpu.usagePercent)">
                    <span>{{ formatMonitorNumber(terminalMonitorData.cpu.usagePercent, 0) }}%</span>
                  </div>
                  <div class="terminal-monitor-usage-main">
                    <div>
                      <span>平均使用率</span>
                      <strong>{{ formatMonitorPercent(terminalMonitorData.cpu.usagePercent) }}</strong>
                    </div>
                    <i><b :style="monitorProgressStyle(terminalMonitorData.cpu.usagePercent)"></b></i>
                    <em>{{ terminalMonitorData.cpu.cores }} CPU</em>
                  </div>
                </div>
                <div class="terminal-monitor-loads">
                  <span><strong>{{ formatMonitorNumber(terminalMonitorData.cpu.load1, 2) }}</strong><em>1分钟</em></span>
                  <span><strong>{{ formatMonitorNumber(terminalMonitorData.cpu.load5, 2) }}</strong><em>5分钟</em></span>
                  <span><strong>{{ formatMonitorNumber(terminalMonitorData.cpu.load15, 2) }}</strong><em>15分钟</em></span>
                </div>
              </section>

              <section class="terminal-monitor-card">
                <h3><AppIcon name="gauge" :size="15" />内存</h3>
                <div class="terminal-monitor-usage">
                  <div class="terminal-monitor-ring" :style="monitorProgressStyle(terminalMonitorData.memory.usagePercent)">
                    <span>{{ formatMonitorNumber(terminalMonitorData.memory.usagePercent, 0) }}%</span>
                  </div>
                  <div class="terminal-monitor-usage-main">
                    <div>
                      <span>RAM</span>
                      <strong>{{ formatMonitorPercent(terminalMonitorData.memory.usagePercent) }}</strong>
                    </div>
                    <i><b :style="monitorProgressStyle(terminalMonitorData.memory.usagePercent)"></b></i>
                    <em>{{ formatMonitorBytes(terminalMonitorData.memory.usedBytes) }} / {{ formatMonitorBytes(terminalMonitorData.memory.totalBytes) }}</em>
                  </div>
                </div>
                <div class="terminal-monitor-memory-extra">
                  <span>剩余 {{ formatMonitorBytes(terminalMonitorData.memory.availableBytes) }}</span>
                  <span>缓存 {{ formatMonitorBytes(terminalMonitorData.memory.cacheBytes) }}</span>
                </div>
              </section>

              <section class="terminal-monitor-card">
                <h3><AppIcon name="network" :size="15" />网络</h3>
                <div v-if="terminalMonitorData.network.length" class="terminal-monitor-network-list">
                  <div v-for="item in terminalMonitorData.network" :key="item.name" class="terminal-monitor-network-item">
                    <strong>{{ item.name }}</strong>
                    <span><em>↑{{ formatMonitorRate(item.txBytesPerSecond) }}</em><em>↓{{ formatMonitorRate(item.rxBytesPerSecond) }}</em></span>
                    <i><b :style="monitorProgressStyle(Math.min(100, (item.rxBytesPerSecond + item.txBytesPerSecond) / 1024))"></b></i>
                  </div>
                </div>
                <p v-else class="terminal-monitor-muted">暂无网卡数据</p>
              </section>

              <section class="terminal-monitor-card">
                <h3><AppIcon name="hardDrive" :size="15" />磁盘</h3>
                <div v-if="terminalMonitorData.disks.length" class="terminal-monitor-disk-list">
                  <div v-for="disk in terminalMonitorData.disks" :key="`${disk.filesystem}-${disk.mountpoint}`" class="terminal-monitor-disk-item">
                    <div>
                      <strong>{{ disk.mountpoint }}</strong>
                      <em>{{ disk.filesystem }} · {{ disk.type }}</em>
                    </div>
                    <span>{{ formatMonitorPercent(disk.usagePercent) }}</span>
                    <i><b :style="monitorProgressStyle(disk.usagePercent)"></b></i>
                    <p>{{ formatMonitorBytes(disk.usedBytes) }} / {{ formatMonitorBytes(disk.totalBytes) }}，可用 {{ formatMonitorBytes(disk.availableBytes) }}</p>
                  </div>
                </div>
                <p v-else class="terminal-monitor-muted">暂无磁盘数据</p>
              </section>
            </template>
          </div>
        </aside>
      </div>
      <section v-if="shouldShowTerminalQuickCommandPanel" class="terminal-quick-panel">
        <el-button
          class="terminal-quick-resizer"
          native-type="button"
          title="调整快捷命令面板高度"
          aria-label="调整快捷命令面板高度"
          :disabled="isTerminalQuickCommandPanelCollapsed"
          @mousedown="startTerminalQuickCommandPanelResize"
        ></el-button>
        <header class="terminal-quick-header">
          <div>
            <strong><AppIcon name="zap" :size="15" />快捷命令</strong>
            <span v-if="isTerminalMultiExecutionEnabled">多执行目标 {{ terminalMultiExecutionTargetCount }} 个</span>
            <span v-else-if="!activeTerminalReady">请选择已连接的终端</span>
            <span v-else>{{ activeTab?.host.name }}</span>
          </div>
          <div class="terminal-quick-actions">
            <el-button native-type="button" title="刷新" aria-label="刷新" :disabled="isTerminalQuickCommandLoading" @click="loadTerminalQuickCommands">
              <AppIcon name="refresh" :size="14" />
            </el-button>
            <el-button native-type="button" title="新增命令" aria-label="新增命令" @click="openTerminalQuickCommandDialog()">
              <AppIcon name="plus" :size="15" />
            </el-button>
            <el-button
              native-type="button"
              :title="isTerminalQuickCommandPanelCollapsed ? '展开快捷命令' : '收起快捷命令'"
              :aria-label="isTerminalQuickCommandPanelCollapsed ? '展开快捷命令' : '收起快捷命令'"
              @click="toggleTerminalQuickCommandPanel"
            >
              <AppIcon name="chevronDown" :size="15" />
            </el-button>
          </div>
        </header>
        <div v-if="!isTerminalQuickCommandPanelCollapsed" class="terminal-quick-body">
          <aside class="terminal-quick-categories">
            <el-button
              native-type="button"
              :class="{ active: terminalQuickCommandCategory === 'all' }"
              @click="terminalQuickCommandCategory = 'all'"
            >
              全部
              <span>{{ terminalQuickCommands.length }}</span>
            </el-button>
            <el-button
              v-for="category in terminalQuickCommandCategories"
              :key="category"
              native-type="button"
              :class="{ active: terminalQuickCommandCategory === category }"
              @click="terminalQuickCommandCategory = category"
            >
              {{ category }}
              <span>{{ terminalQuickCommands.filter((command) => command.category === category).length }}</span>
            </el-button>
          </aside>
          <div class="terminal-quick-content">
            <div class="terminal-quick-toolbar">
              <label>
                <AppIcon name="search" :size="14" />
                <el-input v-model="terminalQuickCommandSearch" type="search" placeholder="搜索名称、分类或命令" clearable />
              </label>
              <span>{{ filteredTerminalQuickCommands.length }} 条</span>
            </div>
            <p v-if="terminalQuickCommandError" class="terminal-quick-error">{{ terminalQuickCommandError }}</p>
            <div class="terminal-quick-list">
              <p v-if="isTerminalQuickCommandLoading" class="terminal-quick-empty">加载中...</p>
              <p v-else-if="!filteredTerminalQuickCommands.length" class="terminal-quick-empty">暂无快捷命令</p>
              <template v-else>
                <article
                  v-for="(command, index) in filteredTerminalQuickCommands"
                  :key="command.id"
                  class="terminal-quick-item"
                  :class="{ disabled: !command.enabled }"
                >
                  <div class="terminal-quick-info">
                    <div>
                      <strong>{{ command.name }}</strong>
                      <span>{{ command.category }}</span>
                    </div>
                    <code>{{ command.command }}</code>
                    <p v-if="command.description">{{ command.description }}</p>
                  </div>
                  <div class="terminal-quick-item-actions">
                    <el-button
                      native-type="button"
                      title="立即执行"
                      aria-label="立即执行"
                      :disabled="!command.enabled || !terminalQuickCommandReady"
                      @click="sendQuickCommandToTerminal(command, true)"
                    >
                      <AppIcon name="zap" :size="14" />
                      <span>立即执行</span>
                    </el-button>
                    <el-button
                      native-type="button"
                      title="追加输入"
                      aria-label="追加输入"
                      :disabled="!command.enabled || !terminalQuickCommandReady"
                      @click="sendQuickCommandToTerminal(command, false)"
                    >
                      <AppIcon name="cornerDownLeft" :size="14" />
                      <span>追加输入</span>
                    </el-button>
                    <el-button
                      native-type="button"
                      :title="command.enabled ? '禁用' : '启用'"
                      :aria-label="command.enabled ? '禁用' : '启用'"
                      @click="toggleTerminalQuickCommand(command)"
                    >
                      <AppIcon :name="command.enabled ? 'eye' : 'eyeOff'" :size="14" />
                    </el-button>
                    <el-button
                      class="move-up"
                      native-type="button"
                      title="上移"
                      aria-label="上移"
                      :disabled="index === 0"
                      @click="moveTerminalQuickCommand(command, -1)"
                    >
                      <AppIcon name="chevronDown" :size="14" />
                    </el-button>
                    <el-button
                      native-type="button"
                      title="下移"
                      aria-label="下移"
                      :disabled="index === filteredTerminalQuickCommands.length - 1"
                      @click="moveTerminalQuickCommand(command, 1)"
                    >
                      <AppIcon name="chevronDown" :size="14" />
                    </el-button>
                    <el-button native-type="button" title="编辑" aria-label="编辑" @click="openTerminalQuickCommandDialog(command)">
                      <AppIcon name="edit" :size="14" />
                    </el-button>
                    <el-button native-type="button" title="删除" aria-label="删除" @click="deleteTerminalQuickCommand(command)">
                      <AppIcon name="trash" :size="14" />
                    </el-button>
                  </div>
                </article>
              </template>
            </div>
          </div>
        </div>
      </section>
    </section>
    <Teleport to="body">
      <div v-if="terminalQuickCommandDialog.visible" class="terminal-quick-dialog-backdrop">
        <article class="terminal-quick-dialog">
          <header class="popup-header">
            <strong>{{ terminalQuickCommandDialog.mode === 'create' ? '新增快捷命令' : '编辑快捷命令' }}</strong>
            <el-button native-type="button" title="关闭" aria-label="关闭" :disabled="terminalQuickCommandDialog.saving" @click="closeTerminalQuickCommandDialog">
              <AppIcon name="x" :size="16" />
            </el-button>
          </header>
          <div class="terminal-quick-dialog-body popup-body">
            <p v-if="terminalQuickCommandDialog.error" class="terminal-quick-error">{{ terminalQuickCommandDialog.error }}</p>
            <label>
              <span>名称</span>
              <el-input v-model="terminalQuickCommandDialog.draft.name" :disabled="terminalQuickCommandDialog.saving" />
            </label>
            <label>
              <span>分类</span>
              <el-select
                v-model="terminalQuickCommandDialog.draft.category"
                filterable
                allow-create
                default-first-option
                :disabled="terminalQuickCommandDialog.saving"
              >
                <el-option v-for="category in terminalQuickCommandCategories" :key="category" :value="category" :label="category" />
              </el-select>
            </label>
            <label>
              <span>命令</span>
              <el-input v-model="terminalQuickCommandDialog.draft.command" type="textarea" :disabled="terminalQuickCommandDialog.saving" :rows="4" />
            </label>
            <label>
              <span>说明</span>
              <el-input v-model="terminalQuickCommandDialog.draft.description" :disabled="terminalQuickCommandDialog.saving" />
            </label>
            <el-checkbox v-model="terminalQuickCommandDialog.draft.enabled" class="terminal-quick-enabled-field" :disabled="terminalQuickCommandDialog.saving">启用</el-checkbox>
          </div>
          <footer class="popup-footer popup-actions">
            <el-button native-type="button" :disabled="terminalQuickCommandDialog.saving" @click="closeTerminalQuickCommandDialog">取消</el-button>
            <el-button class="primary" native-type="button" :disabled="terminalQuickCommandDialog.saving" @click="saveTerminalQuickCommandDialog">
              {{ terminalQuickCommandDialog.saving ? '保存中...' : '保存' }}
            </el-button>
          </footer>
        </article>
      </div>
    </Teleport>
  </main>
</template>
