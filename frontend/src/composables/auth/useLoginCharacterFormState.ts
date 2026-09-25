import { ref, watchPostEffect } from 'vue';

interface LoginCharacterFormTargets {
  getUsernameInput: () => HTMLInputElement | null;
  getPasswordInput: () => HTMLInputElement | null;
  getPasswordLength: () => number;
}

/** Observe the existing Element Plus inputs without changing their behaviour. */
export function useLoginCharacterFormState(targets: LoginCharacterFormTargets) {
  const isTyping = ref(false);
  const showPassword = ref(false);
  const passwordLength = ref(0);

  watchPostEffect((onCleanup) => {
    const username = targets.getUsernameInput();
    const password = targets.getPasswordInput();
    // Track model changes as well as native events (including password-manager autofill).
    const modelLength = targets.getPasswordLength();
    isTyping.value = Boolean(username && document.activeElement === username);
    passwordLength.value = password ? modelLength : 0;

    const focus = () => { isTyping.value = true; };
    const blur = () => { isTyping.value = false; };
    const syncPassword = () => {
      showPassword.value = password?.type === 'text';
      passwordLength.value = password?.value.length ?? 0;
    };
    syncPassword();
    username?.addEventListener('focus', focus);
    username?.addEventListener('blur', blur);
    password?.addEventListener('input', syncPassword);
    password?.addEventListener('change', syncPassword);
    const observer = password ? new MutationObserver(syncPassword) : null;
    if (password) observer?.observe(password, { attributes: true, attributeFilter: ['type'] });

    onCleanup(() => {
      username?.removeEventListener('focus', focus);
      username?.removeEventListener('blur', blur);
      password?.removeEventListener('input', syncPassword);
      password?.removeEventListener('change', syncPassword);
      observer?.disconnect();
    });
  });

  return { isTyping, showPassword, passwordLength };
}
