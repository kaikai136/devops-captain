import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLogDeletion } from '../useLogDeletion';

const mocks = vi.hoisted(() => ({ post: vi.fn(), confirm: vi.fn(), success: vi.fn() }));
vi.mock('../../../api', () => ({ apiPost: mocks.post }));
vi.mock('element-plus', () => ({ ElMessageBox: { confirm: mocks.confirm }, ElMessage: { success: mocks.success } }));

function setup() {
  const reload = vi.fn().mockResolvedValue(undefined);
  const resetPage = vi.fn();
  const onError = vi.fn();
  return { ...useLogDeletion({ endpoint: '/api/system/login-logs/', label: '登录日志', reload, resetPage, onError }), reload, resetPage, onError };
}

describe('log deletion', () => {
  beforeEach(() => { vi.resetAllMocks(); mocks.confirm.mockResolvedValue(undefined); mocks.post.mockResolvedValue({ deletedCount: 2 }); });
  it('deletes exactly the selection and refreshes without resetting the page', async () => {
    const state = setup();
    state.selectionChanged([{ id: 2 }, { id: 4 }]);
    await state.removeSelected();
    expect(mocks.post).toHaveBeenCalledWith('/api/system/login-logs/bulk-delete/', { ids: [2, 4] });
    expect(state.selectedIds.value).toEqual([]);
    expect(state.reload).toHaveBeenCalledOnce();
    expect(state.resetPage).not.toHaveBeenCalled();
  });
  it('does not request when selection is empty or confirmation is cancelled', async () => {
    const state = setup();
    await state.removeSelected();
    expect(mocks.confirm).not.toHaveBeenCalled();
    state.selectionChanged([{ id: 1 }]);
    mocks.confirm.mockRejectedValue('cancel');
    await state.removeSelected();
    expect(mocks.post).not.toHaveBeenCalled();
    expect(state.selectedIds.value).toEqual([1]);
  });
  it('retains selection and reports request failure', async () => {
    const state = setup();
    state.selectionChanged([{ id: 1 }]);
    mocks.post.mockRejectedValue(new Error('denied'));
    await state.removeSelected();
    expect(state.selectedIds.value).toEqual([1]);
    expect(state.onError).toHaveBeenCalledWith('denied');
    expect(state.reload).not.toHaveBeenCalled();
    expect(state.mutationLoading.value).toBe(false);
  });
  it('blocks repeated submissions and selection changes during confirmation', async () => {
    let resolve!: () => void;
    mocks.confirm.mockImplementation(() => new Promise<void>((done) => { resolve = done; }));
    const state = setup();
    state.selectionChanged([{ id: 1 }]);
    const pending = state.removeSelected();
    state.selectionChanged([{ id: 9 }]);
    await state.removeSelected();
    expect(state.selectedIds.value).toEqual([1]);
    expect(mocks.confirm).toHaveBeenCalledOnce();
    resolve(); await pending;
    expect(mocks.post).toHaveBeenCalledOnce();
  });
  it('clears all without filters, warns about scope, and resets the page', async () => {
    const state = setup();
    await state.clearAllLogs();
    expect(mocks.confirm.mock.calls[0][0]).toContain('当前筛选范围外');
    expect(mocks.post).toHaveBeenCalledWith('/api/system/login-logs/clear/', { confirmed: true });
    expect(state.resetPage).toHaveBeenCalledOnce();
    expect(state.reload).toHaveBeenCalledOnce();
  });
});
