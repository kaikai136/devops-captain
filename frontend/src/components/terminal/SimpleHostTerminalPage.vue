<script setup lang="ts">
import Guacamole from 'guacamole-common-js';
import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon } from '@xterm/addon-search';
import { Terminal } from '@xterm/xterm';
import type { IDisposable } from '@xterm/xterm';
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { InputInstance } from 'element-plus';

import AppIcon from '@shared/components/AppIcon.vue';
import AppContextMenu from '@shared/components/context-menu/AppContextMenu.vue';
import type { ContextMenuEntry as SimpleTerminalContextMenuItem } from '@shared/components/context-menu/types';
import { listTerminalTree } from '@features/terminal/api/terminal';
import type { TerminalHost, TerminalTabKind } from '@features/terminal/types';
import {
  buildRdpConnectionQuery,
  buildRdpWebSocketUrl,
  buildTerminalWebSocketUrl,
  formatRdpConnectionErrorMessage,
  parseTerminalHostQuery,
} from '@features/terminal/utils/protocol';
import {
  canUseSimpleHostTerminal,
  findTerminalHostById,
  getSimpleTerminalProtocol,
} from '@features/terminal/utils/simpleHostTerminal';
import {
  CONTROL_C,
  MOUSE_DOUBLE_CLICK_INTERRUPT_SUPPRESSION_MS,
  MOUSE_SELECTION_INTERRUPT_SUPPRESSION_MS,
  TERMINAL_FONT_SIZE_STORAGE_KEY,
  attachTerminalPasteHandler,
  collectTerminalSearchMatches,
  createTerminalScreenOptions,
  getClipboardTextFromPasteEvent,
  getSendableTerminalData,
  getTerminalBufferText,
  getTerminalSearchOptions,
  getTerminalVisibleText,
  handleTerminalCopyShortcut,
  normalizeTerminalPasteText,
  sanitizeTerminalLogFileName,
  selectTerminalSearchMatch,
  toSingleLineTerminalText,
  writeTextToClipboard,
} from '@features/terminal/utils/terminalScreen';
import {
  TERMINAL_FONT_SIZE_DEFAULT,
  TERMINAL_FONT_SIZE_MAX,
  TERMINAL_FONT_SIZE_MIN,
  clampTerminalFontSize,
  createDefaultTerminalSettings,
  normalizeTerminalSettings,
  readStoredTerminalFontSize,
} from '../../utils/terminalSettings';
import { getCurrentUser } from '../../services/auth';
import { getSystemSettingOrNull } from '../../services/system';
import type { TerminalSettingsConfig } from '../../types';

type Status = 'idle' | 'loading' | 'connecting' | 'connected' | 'closed' | 'error' | 'denied';
type GuacamoleClientInstance = InstanceType<typeof Guacamole.Client>;
type GuacamoleWebSocketTunnelInstance = InstanceType<typeof Guacamole.WebSocketTunnel>;
type GuacamoleMouseInstance = InstanceType<typeof Guacamole.Mouse>;
type GuacamoleKeyboardInstance = InstanceType<typeof Guacamole.Keyboard>;
type SearchDirection = 'next' | 'previous';

interface SimpleTerminalContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  selectedText: string;
}

interface SimplePastePromptState {
  visible: boolean;
  x: number;
  y: number;
  value: string;
}


const TERMINAL_SETTINGS_SETTING_KEY = 'terminal_settings';

const host = ref<TerminalHost | null>(null);
const protocol = ref<TerminalTabKind>('ssh');
const status = ref<Status>('idle');
const statusText = ref('准备连接');
const errorMessage = ref('');
const terminalRef = ref<HTMLElement | null>(null);
const rdpRef = ref<HTMLElement | null>(null);
const sessionId = ref<string | null>(null);
const currentCwd = ref('');
const terminalSettings = ref<TerminalSettingsConfig>(createDefaultTerminalSettings());
const isSearchOpen = ref(false);
const searchQuery = ref('');
const searchResultIndex = ref(-1);
const searchResultCount = ref(0);
const searchInputRef = ref<InputInstance | null>(null);
const pasteInputRef = ref<InputInstance | null>(null);
const terminalFontSize = ref(readTerminalFontSize());
const terminalContextMenu = ref<SimpleTerminalContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  selectedText: '',
});
const pastePrompt = ref<SimplePastePromptState>({
  visible: false,
  x: 0,
  y: 0,
  value: '',
});

let xterm: Terminal | null = null;
let fitAddon: FitAddon | null = null;
let searchAddon: SearchAddon | null = null;
let sshSocket: WebSocket | null = null;
let resizeObserver: ResizeObserver | null = null;
let guacClient: GuacamoleClientInstance | null = null;
let guacTunnel: GuacamoleWebSocketTunnelInstance | null = null;
let guacMouse: GuacamoleMouseInstance | null = null;
let guacKeyboard: GuacamoleKeyboardInstance | null = null;
let suppressInterruptUntil = 0;
let reconnectHintShown = false;
let heartbeatTimer: number | null = null;
let terminalDisposables: IDisposable[] = [];

const canDecreaseTerminalFontSize = computed(() => terminalFontSize.value > TERMINAL_FONT_SIZE_MIN);
const canIncreaseTerminalFontSize = computed(() => terminalFontSize.value < TERMINAL_FONT_SIZE_MAX);
const searchResultText = computed(() => {
  if (!searchQuery.value.trim()) return '';
  if (searchResultCount.value <= 0) return '0';
  if (searchResultIndex.value < 0) return String(searchResultCount.value);
  return `${searchResultIndex.value + 1}/${searchResultCount.value}`;
});
const terminalContextMenuItems = computed<SimpleTerminalContextMenuItem[]>(() => {
  const selectedText = terminalContextMenu.value.selectedText.trim();
  const hasSelection = Boolean(selectedText);
  const ready = isSshReady();
  const menuX = terminalContextMenu.value.x;
  const menuY = terminalContextMenu.value.y;
  const items: SimpleTerminalContextMenuItem[] = [];

  if (hasSelection) {
    items.push(
      { id: 'copy-selection', label: '复制', icon: 'copy', enabled: true, shortcut: 'Ctrl+Shift+C', action: () => copyText(selectedText) },
      { id: 'find-selection', label: '查找选中内容', icon: 'search', enabled: true, shortcut: 'Ctrl+Shift+F', action: () => openSearch(selectedText) },
      {
        id: 'online-search',
        label: '在线搜索',
        icon: 'globe',
        enabled: true,
        action: () => undefined,
        children: [
          { id: 'search-selection', label: '搜索选中内容', icon: 'search', enabled: true, action: () => openOnlineSearch(selectedText) },
          { id: 'search-error', label: '搜索报错关键词', icon: 'alert', enabled: true, action: () => openOnlineSearch(`${selectedText} linux error`) },
          { id: 'search-command', label: '搜索命令用法', icon: 'terminal', enabled: true, action: () => openOnlineSearch(`${selectedText} linux command usage`) },
        ],
      },
      {
        id: 'translate',
        label: '翻译',
        icon: 'globe',
        enabled: true,
        action: () => undefined,
        children: [
          { id: 'translate-zh', label: '翻译为中文', icon: 'globe', enabled: true, action: () => openTranslation(selectedText, 'zh-Hans') },
          { id: 'translate-en', label: '翻译为英文', icon: 'globe', enabled: true, action: () => openTranslation(selectedText, 'en') },
        ],
      },
      { id: 'paste-selection', label: '粘贴选定文本到终端', icon: 'clipboard', enabled: ready, separatorBefore: true, action: () => sendTextToTerminal(selectedText) },
      { id: 'paste-selection-single-line', label: '粘贴为单行', icon: 'cornerDownLeft', enabled: ready, action: () => sendTextToTerminal(toSingleLineTerminalText(selectedText)) },
    );
  } else {
    items.push(
      { id: 'paste', label: '粘贴', icon: 'clipboard', enabled: ready, shortcut: 'Ctrl+Shift+V', action: () => pasteClipboardToTerminal(menuX, menuY) },
      { id: 'find', label: '查找...', icon: 'search', enabled: Boolean(xterm), shortcut: 'Ctrl+Shift+F', action: () => openSearch() },
    );
  }

  return [
    ...items,
    getSessionContextMenu(),
    getControlKeyContextMenu(),
    getViewContextMenu(),
    getBufferContextMenu(),
  ];
});

onMounted(() => {
  window.addEventListener('resize', fitActiveSession);
  window.addEventListener('click', closeContextMenu);
  window.addEventListener('keydown', handleWindowKeydown);
  void bootstrap();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', fitActiveSession);
  window.removeEventListener('click', closeContextMenu);
  window.removeEventListener('keydown', handleWindowKeydown);
  cleanupConnections();
});

watch(searchQuery, () => {
  if (!isSearchOpen.value) return;
  searchCurrentTerminal('next', true);
});

async function bootstrap() {
  status.value = 'loading';
  statusText.value = '正在加载主机';
  errorMessage.value = '';

  const hostId = parseTerminalHostQuery(window.location.search);
  if (!hostId) {
    setError('无效的主机 ID');
    return;
  }

  try {
    const current = await getCurrentUser();
    await loadTerminalSettings();
    if (!canUseSimpleHostTerminal(current.user.featurePermissionCodes)) {
      status.value = 'denied';
      statusText.value = '无权限';
      errorMessage.value = '当前角色没有 Web 终端权限。';
      return;
    }

    const groups = await listTerminalTree();
    const selectedHost = findTerminalHostById(groups, hostId);
    if (!selectedHost) {
      setError('主机不可用或无权限访问');
      return;
    }

    host.value = selectedHost;
    protocol.value = getSimpleTerminalProtocol(selectedHost);
    await connect();
  } catch (error) {
    setError(error instanceof Error ? error.message : '终端加载失败');
  }
}

async function connect() {
  const selectedHost = host.value;
  if (!selectedHost) {
    setError('主机不可用或无权限访问');
    return;
  }

  cleanupConnections();
  status.value = 'connecting';
  statusText.value = '连接中';
  errorMessage.value = '';
  await nextTick();

  if (protocol.value === 'rdp') {
    connectRdp(selectedHost);
    return;
  }

  connectSsh(selectedHost);
}

function connectSsh(selectedHost: TerminalHost) {
  terminalFontSize.value = readTerminalFontSize();
  const terminal = markRaw(new Terminal(createTerminalScreenOptions(readTerminalFontSize(), terminalSettings.value.scrollbackLines)));
  const fit = markRaw(new FitAddon());
  const search = markRaw(new SearchAddon({ highlightLimit: 2000 }));
  terminal.loadAddon(fit);
  terminal.loadAddon(search);
  terminal.attachCustomKeyEventHandler((event) => handleTerminalCopyShortcut(event, terminal));
  terminal.writeln('CAPTAIN WEB TERMINAL');
  terminal.writeln(`正在连接 ${selectedHost.name} (${selectedHost.publicIp || selectedHost.privateIp}:${selectedHost.port})...`);
  xterm = terminal;
  fitAddon = fit;
  searchAddon = search;
  suppressInterruptUntil = 0;
  reconnectHintShown = false;

  if (!terminalRef.value) {
    setError('终端容器不可用');
    return;
  }

  terminal.open(terminalRef.value);
  terminalDisposables.push(terminal.onData((data) => {
    if (status.value === 'closed' || status.value === 'error') {
      if (data.includes('\r')) reconnectSshSession();
      return;
    }
    if (status.value === 'connecting') return;

    const sendableData = getSendableTerminalData(data, suppressInterruptUntil);
    if (sendableData) sendTerminalInput(sendableData);
  }));
  terminalDisposables.push(terminal.onResize(({ cols, rows }) => {
    if (sshSocket?.readyState === WebSocket.OPEN) {
      sshSocket.send(JSON.stringify({ type: 'resize', cols, rows }));
    }
  }));
  attachTerminalMouseSelectionGuards(terminalRef.value);
  terminalDisposables.push(attachTerminalPasteHandler(terminalRef.value, (value) => sendPastedTextToTerminal(value)));

  observeResize(terminalRef.value);
  fitActiveSession();

  const socket = new WebSocket(buildTerminalWebSocketUrl(window.location.protocol, window.location.host, selectedHost.id));
  sshSocket = socket;
  socket.addEventListener('open', () => {
    if (sshSocket !== socket) return;
    fitActiveSession();
  });
  socket.addEventListener('message', (event) => {
    if (sshSocket !== socket) return;
    handleSshMessage(event as MessageEvent<string>);
  });
  socket.addEventListener('error', () => {
    if (sshSocket !== socket) return;
    stopHeartbeat();
    status.value = 'error';
    statusText.value = '错误';
    showReconnectHint('WebSocket 连接失败。');
  });
  socket.addEventListener('close', () => {
    if (sshSocket !== socket) return;
    stopHeartbeat();
    if (status.value === 'connected' || status.value === 'connecting') {
      status.value = 'closed';
      statusText.value = '已断开';
      showReconnectHint('连接已关闭。');
    }
  });
}

function handleSshMessage(event: MessageEvent<string>) {
  let message: { type?: string; data?: string; path?: string; message?: string; reason?: string; sessionId?: string; terminalSettings?: Partial<TerminalSettingsConfig> };
  try {
    message = JSON.parse(event.data);
  } catch {
    xterm?.write(event.data);
    return;
  }

  if (message.type === 'ready') {
    if (message.terminalSettings) {
      terminalSettings.value = normalizeTerminalSettings({ ...terminalSettings.value, ...message.terminalSettings });
    }
    status.value = 'connected';
    statusText.value = '已连接';
    sessionId.value = message.sessionId ?? null;
    reconnectHintShown = false;
    fitActiveSession();
    xterm?.focus();
    startHeartbeat();
    return;
  }
  if (message.type === 'pong') {
    return;
  }
  if (message.type === 'output') {
    xterm?.write(message.data ?? '');
    return;
  }
  if (message.type === 'cwd') {
    currentCwd.value = String(message.path || '').trim();
    return;
  }
  if (message.type === 'error') {
    if (message.message === '不支持的终端消息类型') {
      return;
    }
    status.value = 'error';
    statusText.value = '错误';
    errorMessage.value = '';
    showReconnectHint(message.message || '终端连接失败');
    return;
  }
  if (message.type === 'closed') {
    stopHeartbeat();
    status.value = 'closed';
    statusText.value = '已断开';
    showReconnectHint(message.reason || '连接已关闭');
  }
}

async function loadTerminalSettings() {
  const setting = await getSystemSettingOrNull(TERMINAL_SETTINGS_SETTING_KEY);
  terminalSettings.value = normalizeTerminalSettings(setting?.value);
  if (!window.localStorage.getItem(TERMINAL_FONT_SIZE_STORAGE_KEY)) {
    terminalFontSize.value = readTerminalFontSize();
  }
}

function isSshReady() {
  return protocol.value === 'ssh' && status.value === 'connected' && sshSocket?.readyState === WebSocket.OPEN;
}

function startHeartbeat() {
  stopHeartbeat();
  const seconds = terminalSettings.value.webSocketHeartbeatSeconds;
  if (seconds <= 0) return;
  heartbeatTimer = window.setInterval(() => {
    if (sshSocket?.readyState === WebSocket.OPEN) {
      sshSocket.send(JSON.stringify({ type: 'ping' }));
    }
  }, seconds * 1000);
}

function stopHeartbeat() {
  if (heartbeatTimer !== null) {
    window.clearInterval(heartbeatTimer);
    heartbeatTimer = null;
  }
}

function sendTerminalInput(data: string) {
  if (!data || !isSshReady()) return false;
  sshSocket?.send(JSON.stringify({ type: 'input', data }));
  return true;
}

function sendTextToTerminal(value: string) {
  if (sendTerminalInput(value)) xterm?.focus();
}

function sendPastedTextToTerminal(value: string) {
  sendTextToTerminal(normalizeTerminalPasteText(value));
}

function sendControlToTerminal(value: string) {
  sendTextToTerminal(value);
}

async function copyText(value: string) {
  if (!value) return;
  await writeTextToClipboard(value);
}

async function pasteClipboardToTerminal(x?: number, y?: number) {
  if (!isSshReady()) return;
  let value = '';
  try {
    value = (await navigator.clipboard?.readText()) ?? '';
  } catch {
    // Browser clipboard reads are blocked on insecure HTTP origins.
  }
  if (value) {
    sendPastedTextToTerminal(value);
    return;
  }
  openPastePrompt(x, y);
}

function openPastePrompt(x = window.innerWidth / 2 - 160, y = window.innerHeight / 2 - 80) {
  const padding = 12;
  pastePrompt.value = {
    visible: true,
    x: Math.max(padding, Math.min(x, window.innerWidth - 340)),
    y: Math.max(padding, Math.min(y, window.innerHeight - 156)),
    value: '',
  };
  void nextTick(() => pasteInputRef.value?.focus());
}

function closePastePrompt() {
  pastePrompt.value = { visible: false, x: 0, y: 0, value: '' };
}

function submitPastePrompt(value = pastePrompt.value.value) {
  if (value && isSshReady()) sendPastedTextToTerminal(value);
  closePastePrompt();
}

function handlePastePromptPaste(event: ClipboardEvent) {
  const value = getClipboardTextFromPasteEvent(event);
  if (value) submitPastePrompt(value);
}

function attachTerminalMouseSelectionGuards(container: HTMLElement) {
  const handleMouseDown = (event: MouseEvent) => {
    if (event.button !== 0) return;
    suppressMouseInterrupt(MOUSE_SELECTION_INTERRUPT_SUPPRESSION_MS);
    if (event.detail >= 2) suppressMouseInterrupt(MOUSE_DOUBLE_CLICK_INTERRUPT_SUPPRESSION_MS);
  };
  const handleDoubleClick = () => suppressMouseInterrupt(MOUSE_DOUBLE_CLICK_INTERRUPT_SUPPRESSION_MS);
  container.addEventListener('mousedown', handleMouseDown, true);
  container.addEventListener('dblclick', handleDoubleClick, true);
  terminalDisposables.push({
    dispose: () => {
      container.removeEventListener('mousedown', handleMouseDown, true);
      container.removeEventListener('dblclick', handleDoubleClick, true);
    },
  });
}

function suppressMouseInterrupt(duration: number) {
  suppressInterruptUntil = Math.max(suppressInterruptUntil, Date.now() + duration);
}

function showReconnectHint(reason = '') {
  if (reconnectHintShown) return;
  if (reason) xterm?.writeln(`\r\n\x1b[33m${reason}\x1b[0m`);
  xterm?.writeln('\x1b[32m[会话已断开]\x1b[0m');
  xterm?.writeln('\x1b[32m[按回车键重新连接]\x1b[0m');
  reconnectHintShown = true;
}

function reconnectSshSession() {
  if (!host.value || protocol.value !== 'ssh') return;
  status.value = 'connecting';
  statusText.value = '连接中';
  errorMessage.value = '';
  sessionId.value = null;
  currentCwd.value = '';
  reconnectHintShown = false;
  xterm?.writeln('\r\n\x1b[32m[正在重新连接...]\x1b[0m');
  stopHeartbeat();
  if (sshSocket && sshSocket.readyState !== WebSocket.CLOSED) sshSocket.close();
  const socket = new WebSocket(buildTerminalWebSocketUrl(window.location.protocol, window.location.host, host.value.id));
  sshSocket = socket;
  socket.addEventListener('open', () => {
    if (sshSocket !== socket) return;
    fitActiveSession();
  });
  socket.addEventListener('message', (event) => {
    if (sshSocket !== socket) return;
    handleSshMessage(event as MessageEvent<string>);
  });
  socket.addEventListener('error', () => {
    if (sshSocket !== socket) return;
    stopHeartbeat();
    status.value = 'error';
    statusText.value = '错误';
    showReconnectHint('WebSocket 连接失败。');
  });
  socket.addEventListener('close', () => {
    if (sshSocket !== socket) return;
    stopHeartbeat();
    if (status.value === 'connected' || status.value === 'connecting') {
      status.value = 'closed';
      statusText.value = '已断开';
      showReconnectHint('连接已关闭。');
    }
  });
}

function openSearch(initialQuery = '') {
  if (protocol.value !== 'ssh' || !xterm) return;
  closeContextMenu();
  isSearchOpen.value = true;
  if (initialQuery.trim()) searchQuery.value = initialQuery.trim();
  resetSearchResultState();
  focusSearchInputSoon(!initialQuery.trim());
  if (searchQuery.value.trim()) {
    void nextTick(() => searchCurrentTerminal('next', true));
  }
}

function closeSearch() {
  if (!isSearchOpen.value) return;
  isSearchOpen.value = false;
  searchAddon?.clearDecorations();
  xterm?.clearSelection();
  resetSearchResultState();
  xterm?.focus();
}

function resetSearchResultState() {
  searchResultIndex.value = -1;
  searchResultCount.value = 0;
}

function focusSearchInputSoon(select = false) {
  void nextTick(() => {
    const input = searchInputRef.value;
    if (!input) return;
    input.focus();
    if (select) input.input?.select();
  });
}

function searchCurrentTerminal(direction: SearchDirection = 'next', incremental = false) {
  const terminal = xterm;
  const query = searchQuery.value.trim();
  if (!terminal || !query) {
    searchAddon?.clearDecorations();
    terminal?.clearSelection();
    resetSearchResultState();
    return false;
  }

  searchAddon?.clearDecorations();
  const matches = collectTerminalSearchMatches(terminal, query);
  searchResultCount.value = matches.length;
  if (!matches.length) {
    searchResultIndex.value = -1;
    terminal.clearSelection();
    return false;
  }

  const currentIndex = searchResultIndex.value;
  const nextIndex =
    incremental || currentIndex < 0
      ? 0
      : direction === 'previous'
        ? (currentIndex - 1 + matches.length) % matches.length
        : (currentIndex + 1) % matches.length;
  searchResultIndex.value = nextIndex;
  try {
    searchAddon?.findNext(query, getTerminalSearchOptions(false));
  } catch {
    // Manual buffer search above remains the source of truth.
  }
  selectTerminalSearchMatch(terminal, matches[nextIndex]);
  return true;
}

function openOnlineSearch(query: string) {
  const value = query.trim();
  if (!value) return;
  window.open(`https://www.bing.com/search?q=${encodeURIComponent(value)}`, '_blank', 'noopener,noreferrer');
}

function openTranslation(text: string, targetLanguage: 'zh-Hans' | 'en') {
  const value = text.trim();
  if (!value) return;
  window.open(
    `https://www.bing.com/translator?to=${encodeURIComponent(targetLanguage)}&text=${encodeURIComponent(value)}`,
    '_blank',
    'noopener,noreferrer',
  );
}

function getSessionContextMenu(): SimpleTerminalContextMenuItem {
  return {
    id: 'session',
    label: '会话',
    icon: 'server',
    enabled: Boolean(host.value),
    separatorBefore: true,
    action: () => undefined,
    children: [
      {
        id: 'session-reconnect',
        label: '重新连接',
        icon: 'refresh',
        enabled: Boolean(host.value && (status.value === 'closed' || status.value === 'error')),
        action: reconnectSshSession,
      },
      {
        id: 'session-copy-info',
        label: '复制当前主机信息',
        icon: 'copy',
        enabled: Boolean(host.value),
        action: async () => {
          const info = getSessionInfo();
          if (info) await copyText(info);
        },
      },
    ],
  };
}

function getControlKeyContextMenu(): SimpleTerminalContextMenuItem {
  const enabled = isSshReady();
  return {
    id: 'control-keys',
    label: '发送控制键',
    icon: 'terminal',
    enabled,
    action: () => undefined,
    children: [
      { id: 'control-c', label: '中断', icon: 'x', enabled, shortcut: 'Ctrl+C', action: () => sendControlToTerminal(CONTROL_C) },
      { id: 'control-d', label: 'EOF', icon: 'logout', enabled, shortcut: 'Ctrl+D', action: () => sendControlToTerminal('\x04') },
      { id: 'control-z', label: '挂起', icon: 'minimize', enabled, shortcut: 'Ctrl+Z', action: () => sendControlToTerminal('\x1a') },
      { id: 'control-u', label: '清空当前输入', icon: 'trash', enabled, shortcut: 'Ctrl+U', action: () => sendControlToTerminal('\x15') },
      { id: 'control-l', label: '清屏', icon: 'rows', enabled, shortcut: 'Ctrl+L', action: () => sendControlToTerminal('\x0c') },
    ],
  };
}

function getViewContextMenu(): SimpleTerminalContextMenuItem {
  return {
    id: 'view',
    label: '视图',
    icon: 'settings',
    enabled: protocol.value === 'ssh',
    action: () => undefined,
    children: [
      { id: 'font-decrease', label: '字号减小', icon: 'zoomOut', enabled: canDecreaseTerminalFontSize.value, action: decreaseTerminalFontSize },
      { id: 'font-increase', label: '字号增大', icon: 'zoomIn', enabled: canIncreaseTerminalFontSize.value, action: increaseTerminalFontSize },
      {
        id: 'font-reset',
        label: '重置字号',
        icon: 'reset',
        enabled: terminalFontSize.value !== TERMINAL_FONT_SIZE_DEFAULT,
        action: () => setTerminalFontSize(TERMINAL_FONT_SIZE_DEFAULT),
      },
    ],
  };
}

function getBufferContextMenu(): SimpleTerminalContextMenuItem {
  const hasTerminal = protocol.value === 'ssh' && Boolean(xterm);
  const ready = isSshReady();
  return {
    id: 'buffer',
    label: '缓冲区',
    icon: 'rows',
    enabled: hasTerminal,
    action: () => undefined,
    children: [
      { id: 'buffer-clear-screen', label: '清屏', icon: 'rows', enabled: ready, shortcut: 'Ctrl+L', action: () => sendControlToTerminal('\x0c') },
      { id: 'buffer-clear-all', label: '全部清除', icon: 'trash', enabled: hasTerminal, action: () => xterm?.clear() },
      { id: 'buffer-bottom', label: '滚动到底部', icon: 'chevronDown', enabled: hasTerminal, action: () => xterm?.scrollToBottom() },
      {
        id: 'buffer-copy-screen',
        label: '复制当前屏幕',
        icon: 'copy',
        enabled: hasTerminal,
        separatorBefore: true,
        action: async () => {
          if (xterm) await copyText(getTerminalVisibleText(xterm));
        },
      },
      { id: 'buffer-export', label: '导出终端日志...', icon: 'download', enabled: hasTerminal, action: exportTerminalLog },
      { id: 'buffer-select-all', label: '全选', icon: 'scan', enabled: hasTerminal, shortcut: 'Ctrl+Shift+A', separatorBefore: true, action: () => xterm?.selectAll() },
    ],
  };
}

function getSessionInfo() {
  const selectedHost = host.value;
  if (!selectedHost) return '';
  return [
    `主机：${selectedHost.name}`,
    `登录用户：${selectedHost.loginUser || '-'}`,
    `公网 IP：${selectedHost.publicIp || '-'}`,
    `内网 IP：${selectedHost.privateIp || '-'}`,
    `端口：${selectedHost.port}`,
    `当前目录：${currentCwd.value || '-'}`,
    `会话 ID：${sessionId.value || '-'}`,
    `状态：${status.value}`,
  ].join('\n');
}

function exportTerminalLog() {
  if (!xterm || !host.value) return;
  const content = getTerminalBufferText(xterm);
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `${sanitizeTerminalLogFileName(host.value.name)}-${new Date().toISOString().replace(/[:.]/g, '-')}.log`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

function setTerminalFontSize(nextSize: number) {
  const normalized = clampTerminalFontSize(nextSize);
  if (normalized === terminalFontSize.value) return;
  terminalFontSize.value = normalized;
  window.localStorage.setItem(TERMINAL_FONT_SIZE_STORAGE_KEY, String(normalized));
  if (xterm) xterm.options.fontSize = normalized;
  fitActiveSession();
}

function decreaseTerminalFontSize() {
  setTerminalFontSize(terminalFontSize.value - 1);
}

function increaseTerminalFontSize() {
  setTerminalFontSize(terminalFontSize.value + 1);
}

function openSshContextMenu(event: MouseEvent) {
  if (protocol.value !== 'ssh' || !xterm) {
    event.preventDefault();
    return;
  }
  terminalContextMenu.value = {
    visible: true,
    selectedText: xterm.hasSelection() ? xterm.getSelection() : '',
    x: event.clientX,
    y: event.clientY,
  };
}



function closeContextMenu() {
  if (!terminalContextMenu.value.visible) return;
  terminalContextMenu.value = { visible: false, x: 0, y: 0, selectedText: '' };
}

async function runContextMenuItem(item: SimpleTerminalContextMenuItem) {
  if (!item.enabled || item.children?.length) return;
  closeContextMenu();
  await item.action();
}

function handleWindowKeydown(event: KeyboardEvent) {
  if ((event.target as Element | null)?.closest('.shadcn-context-menu-content')) return;
  if (event.key === 'Escape') {
    if (pastePrompt.value.visible) {
      closePastePrompt();
      return;
    }
    if (isSearchOpen.value) {
      closeSearch();
      return;
    }
    closeContextMenu();
    return;
  }

  if (protocol.value !== 'ssh') return;
  const key = event.key.toLowerCase();
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === 'f') {
    event.preventDefault();
    openSearch(xterm?.hasSelection() ? xterm.getSelection() : '');
    return;
  }
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && key === 'v') {
    event.preventDefault();
    void pasteClipboardToTerminal();
  }
}

function readTerminalFontSize() {
  if (typeof window === 'undefined') return TERMINAL_FONT_SIZE_DEFAULT;
  return readStoredTerminalFontSize(window.localStorage.getItem(TERMINAL_FONT_SIZE_STORAGE_KEY), terminalSettings.value.defaultFontSize);
}

function connectRdp(selectedHost: TerminalHost) {
  const container = rdpRef.value;
  if (!container) {
    setError('RDP 容器不可用');
    return;
  }

  container.textContent = '';
  container.tabIndex = 0;
  observeResize(container);

  const tunnel = markRaw(new Guacamole.WebSocketTunnel(buildRdpWebSocketUrl(window.location.protocol, window.location.host, selectedHost.id)));
  const client = markRaw(new Guacamole.Client(tunnel));
  guacTunnel = tunnel;
  guacClient = client;

  const display = client.getDisplay();
  display.onresize = fitActiveSession;
  const displayElement = display.getElement();
  displayElement.classList.add('simple-host-terminal-rdp-display');
  displayElement.tabIndex = 0;
  container.appendChild(displayElement);
  attachRdpInput(displayElement, client);

  client.onstatechange = (state) => {
    if (guacClient !== client) return;
    if (state === Guacamole.Client.State.CONNECTED) {
      status.value = 'connected';
      statusText.value = '已连接';
      fitActiveSession();
      displayElement.focus();
      return;
    }
    if (state === Guacamole.Client.State.DISCONNECTED && status.value !== 'closed') {
      status.value = 'closed';
      statusText.value = '已断开';
    }
  };
  client.onerror = (error) => {
    if (guacClient !== client) return;
    setError(rdpErrorMessage(error));
  };
  tunnel.onerror = (error) => {
    if (guacTunnel !== tunnel) return;
    setError(rdpErrorMessage(error));
  };

  try {
    client.connect(buildRdpConnectionQuery(container.clientWidth, container.clientHeight));
  } catch (error) {
    setError(rdpErrorMessage(error));
  }
}

function attachRdpInput(displayElement: HTMLElement, client: GuacamoleClientInstance) {
  const mouse = markRaw(new Guacamole.Mouse(displayElement));
  mouse.onEach(['mousedown', 'mousemove', 'mouseup'], (event) => {
    if (status.value !== 'connected') return;
    client.sendMouseState((event as Guacamole.Mouse.Event).state, true);
    displayElement.focus();
  });
  mouse.on('mouseout', () => client.getDisplay().showCursor(false));
  guacMouse = mouse;

  const keyboard = markRaw(new Guacamole.Keyboard(displayElement));
  keyboard.onkeydown = (keysym) => {
    if (status.value !== 'connected') return true;
    client.sendKeyEvent(1, keysym);
    return false;
  };
  keyboard.onkeyup = (keysym) => {
    if (status.value !== 'connected') return;
    client.sendKeyEvent(0, keysym);
  };
  guacKeyboard = keyboard;
}

function clearScreen() {
  if (protocol.value === 'ssh') {
    xterm?.clear();
    return;
  }
  rdpRef.value?.focus();
}

function disconnect() {
  status.value = 'closed';
  statusText.value = '已断开';
  cleanupConnections();
}

function cleanupConnections() {
  stopHeartbeat();
  for (const disposable of terminalDisposables) disposable.dispose();
  terminalDisposables = [];
  closeSearch();
  closeContextMenu();
  resizeObserver?.disconnect();
  resizeObserver = null;

  if (sshSocket && sshSocket.readyState !== WebSocket.CLOSED) sshSocket.close();
  sshSocket = null;

  xterm?.dispose();
  xterm = null;
  fitAddon = null;
  searchAddon = null;
  sessionId.value = null;
  currentCwd.value = '';
  reconnectHintShown = false;
  suppressInterruptUntil = 0;

  if (guacKeyboard) {
    guacKeyboard.onkeydown = null;
    guacKeyboard.onkeyup = null;
  }
  guacKeyboard = null;
  guacMouse = null;
  try {
    guacClient?.getDisplay().getElement().remove();
    guacClient?.disconnect();
  } catch {
    // Ignore disconnect races.
  }
  guacClient = null;
  guacTunnel = null;
  if (rdpRef.value) rdpRef.value.textContent = '';
}

function observeResize(element: HTMLElement) {
  resizeObserver?.disconnect();
  resizeObserver = new ResizeObserver(fitActiveSession);
  resizeObserver.observe(element);
}

function fitActiveSession() {
  if (protocol.value === 'ssh') {
    try {
      fitAddon?.fit();
      sendActiveSshResize();
    } catch {
      // xterm can briefly report zero-size containers during first paint.
    }
    return;
  }

  const container = rdpRef.value;
  const display = guacClient?.getDisplay();
  if (!container || !display) return;
  const width = display.getWidth();
  const height = display.getHeight();
  if (!width || !height) return;
  const scale = Math.min(container.clientWidth / width, container.clientHeight / height);
  if (Number.isFinite(scale) && scale > 0) display.scale(scale);
}

function sendActiveSshResize() {
  if (!xterm || sshSocket?.readyState !== WebSocket.OPEN) return;
  sshSocket.send(JSON.stringify({ type: 'resize', cols: xterm.cols, rows: xterm.rows }));
}

function setError(message: string) {
  status.value = 'error';
  statusText.value = '错误';
  errorMessage.value = message;
  xterm?.writeln(`\r\n${message}`);
}

function rdpErrorMessage(error?: unknown) {
  return formatRdpConnectionErrorMessage(error);
}
</script>

<template>
  <main class="simple-host-terminal-page">
    <header class="simple-host-terminal-header">
      <div>
        <strong>终端 - {{ host?.name || '主机' }}</strong>
        <span>主机 ID: {{ host?.id || '-' }}</span>
      </div>
      <nav aria-label="终端操作">
        <span class="simple-host-terminal-status" :class="status">
          <AppIcon :name="status === 'connected' ? 'circleCheck' : status === 'connecting' || status === 'loading' ? 'rotate' : 'alert'" :size="15" />
          {{ statusText }}
        </span>
        <el-button :disabled="!host || status === 'connecting' || status === 'loading' || status === 'denied'" @click="connect">
          <AppIcon name="rotate" :size="15" />
          重新连接
        </el-button>
        <el-button :disabled="status === 'denied' || protocol === 'rdp'" @click="clearScreen">清屏</el-button>
        <el-button :disabled="status === 'denied' || status === 'closed'" @click="disconnect">断开</el-button>
      </nav>
    </header>

    <section class="simple-host-terminal-shell" :class="protocol">
      <AppContextMenu
        :open="terminalContextMenu.visible"
        :items="terminalContextMenuItems"
        :disabled="protocol !== 'ssh'"
        @update:open="!$event && closeContextMenu()"
        @select="runContextMenuItem"
      >
        <div
          v-show="protocol === 'ssh'"
          ref="terminalRef"
          class="simple-host-terminal-xterm"
          @contextmenu="openSshContextMenu($event)"
        ></div>
      </AppContextMenu>
      <div
        v-if="isSearchOpen && protocol === 'ssh'"
        class="simple-host-terminal-search"
        @click.stop
        @mousedown.stop
        @contextmenu.stop
      >
        <AppIcon name="search" :size="14" />
        <el-input
          ref="searchInputRef"
          v-model="searchQuery"
          type="search"
          placeholder="查找当前终端"
          @keydown.enter.prevent="searchCurrentTerminal($event.shiftKey ? 'previous' : 'next')"
          @keydown.esc.prevent.stop="closeSearch"
        />
        <span>{{ searchResultText }}</span>
        <el-button circle title="上一个" aria-label="上一个" :disabled="!searchQuery.trim()" @click="searchCurrentTerminal('previous')">
          <AppIcon name="chevronDown" :size="14" />
        </el-button>
        <el-button circle title="下一个" aria-label="下一个" :disabled="!searchQuery.trim()" @click="searchCurrentTerminal('next')">
          <AppIcon name="chevronDown" :size="14" />
        </el-button>
        <el-button circle title="关闭" aria-label="关闭" @click="closeSearch">
          <AppIcon name="x" :size="14" />
        </el-button>
      </div>
      <div v-show="protocol === 'rdp'" ref="rdpRef" class="simple-host-terminal-rdp"></div>
      <div v-if="errorMessage || status === 'denied'" class="simple-host-terminal-overlay">
        <strong>{{ status === 'denied' ? '没有终端权限' : '连接不可用' }}</strong>
        <span>{{ errorMessage }}</span>
      </div>
      <div
        v-if="pastePrompt.visible"
        class="simple-host-terminal-paste-prompt"
        :style="{ left: `${pastePrompt.x}px`, top: `${pastePrompt.y}px` }"
        @click.stop
        @contextmenu.stop
      >
        <span>在此粘贴后自动发送到终端</span>
        <el-input
          ref="pasteInputRef"
          v-model="pastePrompt.value"
          type="textarea"
          placeholder="按 Ctrl+V，或右键选择粘贴"
          @paste="handlePastePromptPaste"
          @keydown.esc.prevent.stop="closePastePrompt"
          @keydown.ctrl.enter.prevent="submitPastePrompt()"
        />
        <div>
          <el-button type="primary" @click="submitPastePrompt()">发送</el-button>
          <el-button @click="closePastePrompt">取消</el-button>
        </div>
      </div>
    </section>
  </main>
</template>
