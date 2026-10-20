import { computed, ref } from 'vue';
import { describe, expect, it } from 'vitest';
import { keyHarness } from './applicationKeyHarness';

describe('application key selection permissions and current binding', () => {
  it('does not load the selector without use permission but retains an existing reference', async () => {
    const { choices, api } = keyHarness({ canUsePageAction: () => false });
    const keyId = ref(9);
    const state = choices.useApplicationKeyChoices(() => ({ applicationKeyId: 9, applicationKeyName: 'current', username: 'user' }), keyId);
    await state.loadKeys();
    expect(api.selectApplicationKeys).not.toHaveBeenCalled();
    expect(state.selectedKey.value).toEqual({ id: 9, name: 'current', username: 'user' });
    expect(state.canUseKeys.value).toBe(false);
  });
  it('loads fresh usernames, reports failures and supports an empty list', async () => {
    const { choices, api } = keyHarness({ canUsePageAction: () => true });
    const state = choices.useApplicationKeyChoices(() => null, computed(() => 5));
    await state.loadKeys(); expect(state.selectedKey.value.username).toBe('key-user');
    api.selectApplicationKeys.mockRejectedValueOnce(new Error('denied'));
    await state.loadKeys(); expect(state.keyError.value).toContain('denied'); expect(state.loadingKeys.value).toBe(false);
    api.selectApplicationKeys.mockResolvedValueOnce([]);
    await state.loadKeys(); expect(state.keyChoices.value).toEqual([]);
  });
});
