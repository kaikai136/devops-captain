import { computed, onMounted, onUnmounted, ref } from 'vue';

import { AUTH_EXPIRED_EVENT } from '../../api';
import * as authApi from '../../services/auth';
import type { AccountUser, LoginPayload, LoginResult } from '../../types';

export const AUTH_LOGOUT_EVENT_KEY = 'ops-tool.auth.logout-at';

export function useAuthSession({ loadWorkspaceData, clearSessionUi }: { loadWorkspaceData: () => Promise<void>; clearSessionUi: () => void }) {
  const currentUser = ref<AccountUser | null>(null);
  const isLocked = ref(false);
  const hasWorkspaceDataLoaded = ref(false);
  const isAuthReady = ref(false);
  const isAuthenticated = computed(() => Boolean(currentUser.value));
  const shouldRestorePageAfterLogin = ref(false);

  function expireSession() {
    if (!currentUser.value) return;
    shouldRestorePageAfterLogin.value = true;
    currentUser.value = null;
    isLocked.value = false;
    hasWorkspaceDataLoaded.value = false;
    clearSessionUi();
  }

  onMounted(() => {
    if (typeof window !== 'undefined') window.addEventListener(AUTH_EXPIRED_EVENT, expireSession);
  });
  onUnmounted(() => {
    if (typeof window !== 'undefined') window.removeEventListener(AUTH_EXPIRED_EVENT, expireSession);
  });

  async function loadCurrentUser() {
    try {
      const data = await authApi.getCurrentUser();
      currentUser.value = data.user;
      isLocked.value = Boolean(data.locked);
      if (!isLocked.value) {
        await loadUnlockedWorkspace();
      } else {
        hasWorkspaceDataLoaded.value = false;
      }
    } catch {
      currentUser.value = null;
      isLocked.value = false;
      hasWorkspaceDataLoaded.value = false;
    } finally {
      isAuthReady.value = true;
    }
  }

  async function applyAuthenticatedUser(user: AccountUser) {
    currentUser.value = user;
    isLocked.value = false;
    void loadUnlockedWorkspace();
  }

  async function login(payload: LoginPayload): Promise<LoginResult> {
    const data = await authApi.login(payload);
    if ('user' in data) {
      await applyAuthenticatedUser(data.user);
    }
    return data;
  }

  async function verifyTwoFactorLogin(code: string): Promise<AccountUser> {
    const data = await authApi.verifyTwoFactorLogin(code);
    await applyAuthenticatedUser(data.user);
    return data.user;
  }

  async function verifyTwoFactorSetupLogin(code: string): Promise<AccountUser> {
    const data = await authApi.verifyTwoFactorSetupLogin(code);
    await applyAuthenticatedUser(data.user);
    return data.user;
  }

  function updateCurrentUser(user: AccountUser) {
    currentUser.value = user;
  }

  async function refreshCurrentUser() {
    const data = await authApi.getCurrentUser();
    currentUser.value = data.user;
    isLocked.value = Boolean(data.locked);
    return data.user;
  }

  async function lockSession() {
    await authApi.lockSession();
    isLocked.value = true;
  }

  async function unlockSession(password: string) {
    const data = await authApi.unlockSession(password);
    currentUser.value = data.user;
    isLocked.value = Boolean(data.locked);
    await loadUnlockedWorkspace();
    return data.user;
  }

  async function loadUnlockedWorkspace() {
    await loadWorkspaceData();
    hasWorkspaceDataLoaded.value = true;
  }

  async function logout() {
    try {
      await authApi.logout();
    } finally {
      shouldRestorePageAfterLogin.value = false;
      currentUser.value = null;
      isLocked.value = false;
      hasWorkspaceDataLoaded.value = false;
      clearSessionUi();
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(AUTH_LOGOUT_EVENT_KEY, String(Date.now()));
      }
    }
  }

  return {
    currentUser,
    isLocked,
    hasWorkspaceDataLoaded,
    isAuthReady,
    isAuthenticated,
    shouldRestorePageAfterLogin,
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
}
