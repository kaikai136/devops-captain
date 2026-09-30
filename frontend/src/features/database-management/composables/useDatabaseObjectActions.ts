import type { Ref } from 'vue';
import { useAppContext } from '@app/context';
import { errorMessage } from '@shared/utils/errors';
import { runDatabaseObjectAction, type DatabaseAsset } from '../api/databaseManagement';
import type { DatabaseTreeMenuTarget } from '../components/databaseTreeMenu';

export function useDatabaseObjectActions(options: {
  selected: Ref<DatabaseAsset | null>;
  database: Ref<string>;
  schema: Ref<string>;
  target: Ref<DatabaseTreeMenuTarget | null>;
  refresh: () => Promise<void>;
}) {
  const { requestConfirm, showToast } = useAppContext();
  async function executeObjectAction(action: string) {
    const target = options.target.value;
    if (!options.selected.value || !target?.category || target.category === 'query') return;
    const assetId = target.assetId || options.selected.value.id;
    const database = target.database ?? options.database.value;
    const schema = target.schema ?? options.schema.value;
    const payload = { action, database, schema, objectType: target.category, name: target.name, signature: target.signature };
    requestConfirm('确认数据库对象操作', `确定对“${target.name}”执行此操作吗？此操作可能无法撤销。`, '确认', async () => {
      try {
        await runDatabaseObjectAction(assetId, payload);
        if (options.selected.value?.id === assetId && options.database.value === database && options.schema.value === schema) await options.refresh();
        showToast('对象操作完成', target.name);
      } catch (error) { showToast('对象操作失败', errorMessage(error)); }
    });
  }
  return { executeObjectAction };
}
