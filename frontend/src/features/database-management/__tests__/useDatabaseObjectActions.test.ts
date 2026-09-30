import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ref } from 'vue';
import type { DatabaseAsset } from '../api/databaseManagement';
import type { DatabaseTreeMenuTarget } from '../components/databaseTreeMenu';

const mocks = vi.hoisted(() => ({ confirm: vi.fn(), toast: vi.fn(), run: vi.fn() }));
vi.mock('@app/context', () => ({ useAppContext: () => ({ requestConfirm: mocks.confirm, showToast: mocks.toast }) }));
vi.mock('../api/databaseManagement', () => ({ runDatabaseObjectAction: mocks.run }));
import { useDatabaseObjectActions } from '../composables/useDatabaseObjectActions';

describe('confirmed database object actions', () => {
  beforeEach(() => { vi.clearAllMocks(); mocks.run.mockResolvedValue({ ok: true }); });

  function setup() {
    const selected = ref({ id: 1 } as DatabaseAsset);
    const database = ref('shop');
    const schema = ref('public');
    const target = ref<DatabaseTreeMenuTarget | null>({ kind: 'object', assetId: 1, database: 'shop', schema: 'public', name: 'orders', category: 'table' });
    const refresh = vi.fn().mockResolvedValue(undefined);
    return { selected, database, schema, target, refresh, ...useDatabaseObjectActions({ selected, database, schema, target, refresh }) };
  }

  it('does not mutate the database before confirmation', async () => {
    const action = setup();
    await action.executeObjectAction('drop');
    expect(mocks.confirm).toHaveBeenCalledOnce();
    expect(mocks.run).not.toHaveBeenCalled();
  });

  it('captures the target before confirmation and never refreshes another workspace', async () => {
    const action = setup();
    await action.executeObjectAction('drop');
    action.selected.value = { id: 2 } as DatabaseAsset;
    action.database.value = 'other';
    action.target.value = null;
    await mocks.confirm.mock.calls[0][3]();
    expect(mocks.run).toHaveBeenCalledWith(1, expect.objectContaining({ database: 'shop', schema: 'public', name: 'orders', action: 'drop' }));
    expect(action.refresh).not.toHaveBeenCalled();
  });

  it('refreshes the original workspace after confirmed success', async () => {
    const action = setup();
    await action.executeObjectAction('truncate');
    await mocks.confirm.mock.calls[0][3]();
    expect(action.refresh).toHaveBeenCalledOnce();
  });
});
