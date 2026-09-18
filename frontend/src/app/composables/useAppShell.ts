import { computed, onMounted, onUnmounted, ref, watch, type ComputedRef, type Ref } from 'vue';

import { apiGet } from '../../api';
import { useFeedback } from '../../composables/app/useFeedback';
import { buildTemplateVariables, renderTemplate, useSiteSettings } from '../../composables/features/useSiteSettings';
import type { HostTransferFormat, useHostManager } from '../../composables/features/useHostManager';
import type { AccountUser, ToolKey } from '../../types';
import { setupClickWords, setupPointerTrail } from '../../utils/effects';
import { applyUiTheme } from '../../utils/uiTheme';

type HostManager = ReturnType<typeof useHostManager>;

const xlsxMimeType = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

type UseAppShellOptions = {
  activeTool: Ref<ToolKey>;
  currentUser: Ref<AccountUser | null>;
  isAuthenticated: ComputedRef<boolean>;
  isLocked: Ref<boolean>;
  loadCurrentUser: () => Promise<void>;
  loadAuthEntries: () => Promise<void>;
  cleanupPageState: () => void;
  downloadHostImportTemplate: HostManager['downloadHostImportTemplate'];
  exportHostManagement: HostManager['exportHostManagement'];
  importHostManagement: HostManager['importHostManagement'];
};

export function useAppShell({
  activeTool,
  currentUser,
  isAuthenticated,
  isLocked,
  loadCurrentUser,
  loadAuthEntries,
  cleanupPageState,
  downloadHostImportTemplate,
  exportHostManagement,
  importHostManagement,
}: UseAppShellOptions) {
  const feedback = useFeedback(activeTool);
  const { showToast, copyText, requestConfirm, clearFeedback, cleanupFeedback } = feedback;

  const localIp = ref('198.18.0.1');
  const selectedHost = ref('192.168.1.1');
  const templateNow = ref(new Date());
  const authImportFile = ref<HTMLInputElement | null>(null);
  const passwordImportFile = ref<HTMLInputElement | null>(null);
  const hostImportFile = ref<HTMLInputElement | null>(null);
  const hostTransferDialog = ref<'import' | 'export' | null>(null);
  const hostTransferFormat = ref<HostTransferFormat>('json');
  const imageInput = ref<HTMLInputElement | null>(null);

  const siteSettings = useSiteSettings({ showToast });
  const { siteIdentity, uiTheme, loadPublicSiteSettings } = siteSettings;
  const hostImportAccept = computed(() =>
    hostTransferFormat.value === 'excel' ? `${xlsxMimeType},.xlsx` : 'application/json,.json,.enc.json',
  );

  async function loadLocalIp() {
    try {
      const data = await apiGet<{ ip: string }>('/api/local-ip/');
      localIp.value = data.ip;
    } catch {
      localIp.value = '198.18.0.1';
    }
  }

  function renderSystemTemplate(template: string, generatedAt = '') {
    return renderTemplate(
      template,
      buildTemplateVariables({
        siteIdentity: siteIdentity.value,
        user: currentUser.value,
        localIp: localIp.value,
        generatedAt,
        now: templateNow.value,
      }),
    );
  }

  function openHostTransferDialog(mode: 'import' | 'export') {
    hostTransferDialog.value = mode;
    hostTransferFormat.value = 'excel';
  }

  function closeHostTransferDialog() {
    hostTransferDialog.value = null;
  }

  async function confirmHostTransfer() {
    if (hostTransferDialog.value === 'export') {
      await exportHostManagement(hostTransferFormat.value);
      closeHostTransferDialog();
      return;
    }
    if (hostTransferDialog.value === 'import') {
      hostImportFile.value?.click();
      closeHostTransferDialog();
    }
  }

  function triggerHostImportFile() {
    hostTransferFormat.value = 'excel';
    hostImportFile.value?.click();
  }

  function triggerHostRestoreFile() {
    hostTransferFormat.value = 'json';
    hostImportFile.value?.click();
  }

  async function importSelectedHostManagement(event: Event) {
    await importHostManagement(event, hostTransferFormat.value);
  }

  watch(
    () => siteIdentity.value.browserTitle,
    (title) => {
      document.title = title || siteIdentity.value.appName;
    },
    { immediate: true },
  );

  watch(
    uiTheme,
    (theme) => {
      if (typeof document !== 'undefined' && document.documentElement) {
        applyUiTheme(document.documentElement, theme);
      }
    },
    { deep: true, immediate: true },
  );

  let cleanupClickWords: (() => void) | undefined;
  let cleanupPointerTrail: (() => void) | undefined;
  let authTimer: number | undefined;
  let templateTimer: number | undefined;

  onMounted(async () => {
    await loadPublicSiteSettings();
    cleanupClickWords = setupClickWords();
    cleanupPointerTrail = setupPointerTrail();
    await loadCurrentUser();
    templateTimer = window.setInterval(() => {
      templateNow.value = new Date();
    }, 1000);
    authTimer = window.setInterval(() => {
      if (isAuthenticated.value && !isLocked.value && activeTool.value === 'auth') loadAuthEntries();
    }, 1000);
  });

  onUnmounted(() => {
    cleanupClickWords?.();
    cleanupPointerTrail?.();
    window.clearInterval(authTimer);
    window.clearInterval(templateTimer);
    cleanupPageState();
    cleanupFeedback();
  });

  const state = {
    localIp,
    ...siteSettings,
    renderSystemTemplate,
    showToast,
    authImportFile,
    passwordImportFile,
    hostImportFile,
    hostImportAccept,
    hostTransferDialog,
    hostTransferFormat,
    triggerHostImportFile,
    triggerHostRestoreFile,
    openHostTransferDialog,
    closeHostTransferDialog,
    confirmHostTransfer,
    downloadHostImportTemplate,
    importHostManagement: importSelectedHostManagement,
    imageInput,
    selectedHost,
    copyText,
    requestConfirm,
  };

  return {
    state,
    showToast,
    copyText,
    requestConfirm,
    clearFeedback,
    loadLocalIp,
  };
}
