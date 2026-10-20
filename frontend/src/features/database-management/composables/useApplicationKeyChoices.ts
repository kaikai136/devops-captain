import { computed, onMounted, ref, type Ref } from 'vue';
import { useAppContext } from '@app/context';
import { selectApplicationKeys, type ApplicationKeyChoice } from '../api/applicationKeys';
import type { DatabaseAsset } from '../api/databaseManagement';
import { errorMessage } from '@shared/utils/errors';

export function useApplicationKeyChoices(asset: () => DatabaseAsset | null | undefined, keyId: Ref<number | null | undefined>) {
  const { canUsePageAction } = useAppContext();
  const canUseKeys = computed(() => canUsePageAction('applicationKeys', 'use'));
  const keys = ref<ApplicationKeyChoice[]>([]);
  const loadingKeys = ref(false);
  const keyError = ref('');
  const keyChoices = computed(() => {
    const current = asset();
    if (!current?.applicationKeyId || keys.value.some(key => key.id === current.applicationKeyId)) return keys.value;
    return [...keys.value, { id: current.applicationKeyId, name: current.applicationKeyName || `密钥 ${current.applicationKeyId}`, username: current.username }];
  });
  const selectedKey = computed(() => keyChoices.value.find(key => key.id === keyId.value));
  async function loadKeys() {
    if (!canUseKeys.value || loadingKeys.value) return;
    loadingKeys.value = true; keyError.value = '';
    try { keys.value = await selectApplicationKeys(); }
    catch (error) { keyError.value = errorMessage(error); }
    finally { loadingKeys.value = false; }
  }
  onMounted(loadKeys);
  return { canUseKeys, keyChoices, selectedKey, loadingKeys, keyError, loadKeys };
}
