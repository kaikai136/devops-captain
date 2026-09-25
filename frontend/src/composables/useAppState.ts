import { computed } from 'vue';

import { useAppShell } from '../app/composables/useAppShell';
import { usePageState } from '../app/composables/usePageState';
import { useSessionState } from '../app/composables/useSessionState';
import { useAuthenticator } from './features/useAuthenticator';
import { useHostManager } from './features/useHostManager';
import { useIpScanner } from './features/useIpScanner';
import { useMachineProbe } from './features/useMachineProbe';
import { usePasswordManager } from './features/usePasswordManager';
import { useSubnetCalculator } from './features/useSubnetCalculator';
import { useWatermarkSettings, watermarkAppliesToPage } from './features/useWatermarkSettings';

export function useAppState() {
  let pages!: ReturnType<typeof usePageState>;
  let appShell!: ReturnType<typeof useAppShell>;
  let hostManager!: ReturnType<typeof useHostManager>;
  let machineProbe!: ReturnType<typeof useMachineProbe>;
  let passwordManager!: ReturnType<typeof usePasswordManager>;
  let authenticator!: ReturnType<typeof useAuthenticator>;
  let watermarkSettings!: ReturnType<typeof useWatermarkSettings>;

  async function loadWorkspaceData() {
    await Promise.allSettled([
      appShell.loadLocalIp(),
      appShell.state.loadSiteSettings(),
      authenticator.loadAuthEntries(),
      passwordManager.loadPasswords(),
      watermarkSettings.loadWatermarkSetting(),
      hostManager.loadHostManagement(),
      subnetCalculator.calculateSubnet(false),
    ]);
  }

  function clearSessionUi() {
    appShell.clearFeedback();
    authenticator.qrPreview.value = null;
  }

  function selectHost(ip: string) {
    appShell.state.selectedHost.value = ip;
    machineProbe.setProbeHost(ip);
  }

  const session = useSessionState({
    loadWorkspaceData,
    clearSessionUi,
    onAuthenticated: (restorePreviousPage) => {
      if (!restorePreviousPage) pages.selectDefaultTool();
    },
  });

  pages = usePageState(session, {
    selectHost,
    runPing: () => machineProbe.runPing(),
  });

  appShell = useAppShell({
    activeTool: pages.activeTool,
    currentUser: session.state.currentUser,
    isAuthenticated: session.state.isAuthenticated,
    isLocked: session.state.isLocked,
    loadCurrentUser: session.state.loadCurrentUser,
    loadAuthEntries: () => authenticator.loadAuthEntries(),
    cleanupPageState: pages.cleanup,
    downloadHostImportTemplate: () => hostManager.downloadHostImportTemplate(),
    exportHostManagement: (format) => hostManager.exportHostManagement(format),
    importHostManagement: (event, format) => hostManager.importHostManagement(event, format),
  });

  hostManager = useHostManager({
    showToast: appShell.showToast,
    requestConfirm: appShell.requestConfirm,
    currentUsername: () => session.currentHostCreatorUsername.value,
  });

  machineProbe = useMachineProbe({
    showToast: appShell.showToast,
    selectedHost: appShell.state.selectedHost,
  });

  const ipScanner = useIpScanner({ showToast: appShell.showToast, selectHost });
  const subnetCalculator = useSubnetCalculator({ showToast: appShell.showToast });

  passwordManager = usePasswordManager({
    showToast: appShell.showToast,
    copyText: appShell.copyText,
    requestConfirm: appShell.requestConfirm,
    passwordImportFile: appShell.state.passwordImportFile,
  });

  authenticator = useAuthenticator({
    showToast: appShell.showToast,
    copyText: appShell.copyText,
    requestConfirm: appShell.requestConfirm,
    authImportFile: appShell.state.authImportFile,
    imageInput: appShell.state.imageInput,
  });

  watermarkSettings = useWatermarkSettings({
    showToast: appShell.showToast,
    renderWatermarkText: appShell.state.renderSystemTemplate,
  });

  const shouldShowWatermark = computed(() => watermarkAppliesToPage(watermarkSettings.watermarkConfig.value, pages.activeTool.value));
  const { setProbeHost: _setProbeHost, ...machineProbeState } = machineProbe;
  const { loadPasswords: _loadPasswords, ...passwordState } = passwordManager;
  const { loadAuthEntries: _loadAuthEntries, ...authenticatorState } = authenticator;

  return {
    ...hostManager,
    ...machineProbeState,
    ...ipScanner,
    ...subnetCalculator,
    ...passwordState,
    ...authenticatorState,
    ...watermarkSettings,
    ...session.state,
    ...pages.state,
    ...appShell.state,
    selectHost,
    shouldShowWatermark,
  };
}

export type AppState = ReturnType<typeof useAppState>;
