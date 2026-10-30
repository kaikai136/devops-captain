import { ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { apiPost } from '../../api';
import { errorMessage } from '../utils/errors';

export function useLogDeletion(options: {
  endpoint: string;
  label: string;
  reload: () => Promise<void>;
  resetPage: () => void;
  onError: (message: string) => void;
}) {
  const selectedIds = ref<number[]>([]);
  const mutationLoading = ref(false);
  function clearSelection() { selectedIds.value = []; }
  function selectionChanged(rows: { id: number }[]) {
    if (mutationLoading.value) return;
    selectedIds.value = rows.map((row) => row.id);
  }
  async function execute(clear: boolean) {
    if (mutationLoading.value || (!clear && !selectedIds.value.length)) return;
    mutationLoading.value = true;
    const ids = [...selectedIds.value];
    try {
      try {
        await ElMessageBox.confirm(clear
          ? `将删除全部${options.label}，包括当前筛选范围外的记录，且不可恢复。确定继续吗？`
          : `确定删除选中的 ${ids.length} 条${options.label}吗？`, clear ? '清空确认' : '删除确认', {
          type: 'warning', confirmButtonText: clear ? '确认清空' : '确认删除', cancelButtonText: '取消',
        });
      } catch { return; }
      const result = await apiPost<{ deletedCount: number }>(`${options.endpoint}${clear ? 'clear' : 'bulk-delete'}/`, clear ? { confirmed: true } : { ids });
      clearSelection();
      if (clear) options.resetPage();
      await options.reload();
      ElMessage.success(`已删除 ${result.deletedCount} 条日志`);
    } catch (error) { options.onError(errorMessage(error)); }
    finally { mutationLoading.value = false; }
  }
  return { selectedIds, mutationLoading, clearSelection, selectionChanged,
    removeSelected: () => execute(false), clearAllLogs: () => execute(true) };
}
