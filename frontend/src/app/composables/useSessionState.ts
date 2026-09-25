import { computed, ref, watch } from 'vue';

import { useAuthSession } from '../../composables/app/useAuthSession';

type UseSessionStateOptions = {
  loadWorkspaceData: () => Promise<void>;
  clearSessionUi: () => void;
  onAuthenticated: (restorePreviousPage: boolean) => void;
};

export function useSessionState({ loadWorkspaceData, clearSessionUi, onAuthenticated }: UseSessionStateOptions) {
  const authSession = useAuthSession({ loadWorkspaceData, clearSessionUi });
  const {
    currentUser,
    isLocked,
    hasWorkspaceDataLoaded,
    isAuthReady,
    isAuthenticated,
    shouldRestorePageAfterLogin,
    loadCurrentUser,
    login: authLogin,
    verifyTwoFactorLogin: authVerifyTwoFactorLogin,
    verifyTwoFactorSetupLogin: authVerifyTwoFactorSetupLogin,
    updateCurrentUser,
    refreshCurrentUser,
    lockSession,
    unlockSession,
    logout,
  } = authSession;

  const currentHostCreatorUsername = ref<string | null>(null);
  const currentPermissionCodes = computed(() => new Set(currentUser.value?.featurePermissionCodes ?? []));

  watch(
    currentUser,
    (user) => {
      currentHostCreatorUsername.value = user?.username ?? null;
    },
    { immediate: true },
  );

  async function login(...args: Parameters<typeof authLogin>) {
    const result = await authLogin(...args);
    if ('user' in result) finishAuthentication();
    return result;
  }

  async function verifyTwoFactorLogin(...args: Parameters<typeof authVerifyTwoFactorLogin>) {
    const user = await authVerifyTwoFactorLogin(...args);
    finishAuthentication();
    return user;
  }

  async function verifyTwoFactorSetupLogin(...args: Parameters<typeof authVerifyTwoFactorSetupLogin>) {
    const user = await authVerifyTwoFactorSetupLogin(...args);
    finishAuthentication();
    return user;
  }

  function finishAuthentication() {
    const restorePreviousPage = shouldRestorePageAfterLogin.value;
    shouldRestorePageAfterLogin.value = false;
    onAuthenticated(restorePreviousPage);
  }

  function canUsePageAction(pageKey: string, actionKey: string) {
    const user = currentUser.value;
    if (!user) return false;
    if (user.is_superuser || user.is_staff) return true;
    return currentPermissionCodes.value.has(`action_${pageKey}_${actionKey}`);
  }

  function canUseAnyPageAction(pageKey: string, actionKeys: string[]) {
    return actionKeys.some((actionKey) => canUsePageAction(pageKey, actionKey));
  }

  function canAccessPage(pageKey: string) {
    const user = currentUser.value;
    if (!user) return false;
    if (user.is_superuser || user.is_staff) return true;
    if (pageKey === 'sessionAudits') {
      return currentPermissionCodes.value.has('action_hosts_session_audit');
    }
    return currentPermissionCodes.value.has(`access_${pageKey}`);
  }

  function canAccessNavItem(pageKey: string, permissionCodes: Set<string>) {
    if (pageKey === 'sessionAudits') {
      return permissionCodes.has('action_hosts_session_audit');
    }
    return permissionCodes.has(`access_${pageKey}`);
  }

  const state = {
    currentUser,
    isLocked,
    hasWorkspaceDataLoaded,
    canAccessPage,
    canUsePageAction,
    canUseAnyPageAction,
    isAuthReady,
    isAuthenticated,
    loadCurrentUser,
    login,
    verifyTwoFactorLogin,
    verifyTwoFactorSetupLogin,
    updateCurrentUser,
    refreshCurrentUser,
    lockSession,
    unlockSession,
    logout,
  };

  return {
    state,
    currentHostCreatorUsername,
    currentPermissionCodes,
    canAccessNavItem,
  };
}
