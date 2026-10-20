<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useAppContext } from '@app/context';
import AppIcon from '@shared/components/AppIcon.vue';
import SystemSearchPanel from '@shared/components/SystemSearchPanel.vue';
import { createApplicationKey, deleteApplicationKey, listApplicationKeys, updateApplicationKey, type ApplicationKey, type ApplicationKeyPayload } from '../../features/database-management/api/applicationKeys';
import { errorMessage } from '@shared/utils/errors';

const { canUsePageAction } = useAppContext();
const can = (action: string) => canUsePageAction('applicationKeys', action);
const keys = ref<ApplicationKey[]>([]);
const search = ref('');
const loading = ref(false);
const saving = ref(false);
const deleting = ref(false);
const fullscreen = ref(false);
const message = ref('');
const dialog = ref(false);
const editing = ref<ApplicationKey | null>(null);
const confirmDelete = ref<ApplicationKey | null>(null);
const emptyForm = (): ApplicationKeyPayload => ({ name: '', username: '', password: '', remark: '' });
const form = ref(emptyForm());
const filtered = computed(() => {
  const query = search.value.trim().toLowerCase();
  return keys.value.filter(key => [key.name, key.id, key.username, key.remark].some(value => String(value).toLowerCase().includes(query)));
});
async function loadKeys() {
  if (!can('view') || loading.value) return;
  loading.value = true; message.value = '';
  try { keys.value = await listApplicationKeys(); }
  catch (error) { message.value = errorMessage(error); }
  finally { loading.value = false; }
}
function openDialog(key: ApplicationKey | null = null) {
  if (!can(key ? 'edit' : 'create')) return;
  editing.value = key;
  form.value = key ? { name: key.name, username: key.username, password: '', remark: key.remark } : emptyForm();
  message.value = ''; dialog.value = true;
}
async function saveKey() {
  if (saving.value || !can(editing.value ? 'edit' : 'create')) return;
  const value = { ...form.value, name: form.value.name.trim(), username: form.value.username.trim(), remark: form.value.remark.trim() };
  if (!value.name || (!editing.value && !value.password)) { message.value = !value.name ? '请输入密钥名称' : '请输入密码'; return; }
  saving.value = true; message.value = '';
  try {
    if (editing.value) await updateApplicationKey(editing.value.id, value);
    else await createApplicationKey(value);
    dialog.value = false; form.value = emptyForm(); await loadKeys();
  } catch (error) { message.value = errorMessage(error); }
  finally { saving.value = false; }
}
async function removeKey() {
  if (!confirmDelete.value || deleting.value || !can('delete')) return;
  deleting.value = true; message.value = '';
  try { await deleteApplicationKey(confirmDelete.value.id); confirmDelete.value = null; await loadKeys(); }
  catch (error) { message.value = errorMessage(error); }
  finally { deleting.value = false; }
}
onMounted(loadKeys);
</script>

<template>
  <section class="account-page app-management-page application-key-page" :class="{ fullscreen }">
    <SystemSearchPanel>
      <div class="account-toolbar">
        <el-input v-model="search" class="account-toolbar-search" placeholder="输入名称 / ID / 用户 / 备注搜索" clearable aria-label="搜索应用密钥" />
        <div class="account-toolbar-actions">
          <el-button v-if="can('create')" type="primary" @click="openDialog()"><AppIcon name="plus" :size="16" />新增密钥</el-button>
          <el-button :loading="loading" :disabled="!can('view')" aria-label="刷新" @click="loadKeys"><AppIcon name="refresh" :size="16" /></el-button>
          <el-button :aria-label="fullscreen ? '退出全屏' : '全屏'" @click="fullscreen = !fullscreen"><AppIcon :name="fullscreen ? 'minimize' : 'maximize'" :size="18" /></el-button>
        </div>
      </div>
    </SystemSearchPanel>
    <article class="panel account-panel app-management-card">
      <div class="app-management-heading account-list-heading"><div><h2>应用密钥</h2><span>统一管理数据库用户名与密码</span></div></div>
      <p class="account-stats-line"><span>共 {{ keys.length }} 个密钥</span><span v-if="loading">加载中</span></p>
      <p v-if="message && !dialog && !confirmDelete" class="account-message" role="alert">{{ message }}</p>
      <div v-if="can('view')" class="account-table-wrap app-data-table-wrap">
        <el-table :data="filtered" row-key="id" class="account-table app-data-table" empty-text="没有匹配的应用密钥">
          <el-table-column label="名称" min-width="160"><template #default="{ row }"><div class="account-name"><strong>{{ row.name }}</strong><span>ID {{ row.id }}</span></div></template></el-table-column>
          <el-table-column label="用户" min-width="120"><template #default="{ row }">{{ row.username || '未设置（仅密码认证）' }}</template></el-table-column>
          <el-table-column label="密码状态" min-width="100"><template #default="{ row }"><el-tag :type="row.hasPassword ? 'success' : 'warning'" size="small">{{ row.hasPassword ? '已设置' : '未设置' }}</el-tag></template></el-table-column>
          <el-table-column prop="connectionCount" label="关联连接数" min-width="110" />
          <el-table-column prop="remark" label="备注" min-width="170" show-overflow-tooltip />
          <el-table-column label="操作" width="140" fixed="right"><template #default="{ row }"><div class="account-actions">
            <el-button v-if="can('edit')" type="primary" size="small" @click="openDialog(row)">编辑</el-button>
            <el-button v-if="can('delete')" type="danger" size="small" @click="message = ''; confirmDelete = row">删除</el-button>
          </div></template></el-table-column>
        </el-table>
      </div>
      <div v-else class="permission-empty">暂无查看权限</div>
    </article>
    <el-dialog v-model="dialog" class="account-popup-dialog application-key-dialog" :title="editing ? '编辑应用密钥' : '新增应用密钥'" width="min(560px, calc(100vw - 28px))" :close-on-click-modal="false" :show-close="!saving" :close-on-press-escape="!saving" @closed="form = emptyForm()">
      <el-form :model="form" label-position="top" :disabled="saving" class="popup-body popup-form-grid account-popup-form" @submit.prevent>
        <el-form-item label="名称" required><el-input v-model="form.name" maxlength="120" autofocus /></el-form-item>
        <el-form-item label="用户"><el-input v-model="form.username" maxlength="120" placeholder="Redis 仅密码认证时可留空" /></el-form-item>
        <el-form-item label="密码" class="account-form-full" :required="!editing"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" :placeholder="editing ? '留空保留原密码' : '请输入密码'" /></el-form-item>
        <el-form-item label="备注" class="account-form-full"><el-input v-model="form.remark" type="textarea" :rows="3" /></el-form-item>
        <p v-if="message" class="account-message" role="alert">{{ message }}</p>
      </el-form>
      <template #footer><el-button :disabled="saving" @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveKey">保存</el-button></template>
    </el-dialog>
    <el-dialog :model-value="!!confirmDelete" class="account-popup-dialog" title="删除应用密钥" width="min(420px, calc(100vw - 28px))" :close-on-click-modal="false" :show-close="!deleting" :close-on-press-escape="!deleting" @close="confirmDelete = null">
      <p v-if="confirmDelete?.connectionCount">该密钥关联 {{ confirmDelete.connectionCount }} 个连接，请先修改相关连接的认证方式或所选密钥，再删除。</p>
      <p v-else>确定删除应用密钥「{{ confirmDelete?.name }}」吗？</p>
      <p v-if="message" class="account-message" role="alert">{{ message }}</p>
      <template #footer><el-button :disabled="deleting" @click="confirmDelete = null">取消</el-button><el-button type="danger" :loading="deleting" :disabled="!!confirmDelete?.connectionCount" @click="removeKey">确定删除</el-button></template>
    </el-dialog>
  </section>
</template>

<style scoped>
@media (max-width: 640px) {
  .application-key-page .account-toolbar { flex-wrap: wrap; gap: 10px; }
  .application-key-page .account-toolbar-search { width: 100%; }
}
</style>
