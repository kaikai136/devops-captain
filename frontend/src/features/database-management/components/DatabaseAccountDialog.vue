<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { errorMessage } from '@shared/utils/errors';
import { listDatabaseAccounts, manageDatabaseAccount, type DatabaseAccount } from '../api/databaseManagement';

const props = defineProps<{ modelValue: boolean; assetId: number; database: string; dbType: string; schema: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();
const accounts = ref<DatabaseAccount[]>([]);
const loading = ref(false);
const editing = ref<DatabaseAccount | null>(null);
const formOpen = ref(false);
const form = ref({ name: '', host: '%', password: '', schema: '', grants: [] as string[], revokes: [] as string[], addRoles: [] as string[], removeRoles: [] as string[] });
const roleOptions = computed(() => accounts.value[0]?.availableRoles || []);
const privileges = computed(() => accounts.value[0]?.capabilities?.grants || (['postgresql', 'kingbase'].includes(props.dbType) ? ['CONNECT', 'USAGE', 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'EXECUTE'] : props.dbType === 'sqlserver' ? ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'ALTER', 'EXECUTE'] : ['oracle', 'dameng'].includes(props.dbType) ? ['CONNECT'] : ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP', 'EXECUTE']));

watch(() => props.modelValue, open => { if (open) void load(); });
async function load() { loading.value = true; try { accounts.value = await listDatabaseAccounts(props.assetId, props.database, props.schema); } catch (error) { ElMessage.error(errorMessage(error)); } finally { loading.value = false; } }
function openAccount(item?: DatabaseAccount) { formOpen.value = true; editing.value = item || null; form.value = { name: item?.name || '', host: item?.host || '%', password: '', schema: props.schema, grants: [], revokes: [], addRoles: [], removeRoles: [] }; }
async function save() {
  try {
    if (form.value.grants.some(value => form.value.revokes.includes(value)) || form.value.addRoles.some(value => form.value.removeRoles.includes(value))) {
      ElMessage.error('同一权限或角色不能同时授予和撤销'); return;
    }
    if (!window.confirm(`确定保存账号“${form.value.name}”及其权限配置吗？`)) return;
    const assetId = props.assetId;
    const data = { database: props.database, ...form.value };
    const roles = roleOptions.value.map(item => ({ ...item }));
    if (!editing.value) {
      await manageDatabaseAccount(assetId, { action: 'create', ...data });
      editing.value = { name: data.name, host: data.host, roles: [], permissions: [] };
    } else if (data.password) await manageDatabaseAccount(assetId, { action: 'password', ...data }, 'PUT');
    if (data.grants.length) await manageDatabaseAccount(assetId, { action: 'grant', ...data }, 'PUT');
    if (data.revokes.length) await manageDatabaseAccount(assetId, { action: 'revoke', ...data, grants: data.revokes }, 'PUT');
    for (const [action, selected] of [['grant_role', data.addRoles], ['revoke_role', data.removeRoles]] as const) {
      for (const key of selected) {
        const role = roles.find(item => JSON.stringify([item.name, item.host]) === key);
        if (role) await manageDatabaseAccount(assetId, { action, ...data, role: role.name, roleHost: role.host }, 'PUT');
      }
    }
    editing.value = null; formOpen.value = false; await load(); ElMessage.success('数据库账号已保存');
  } catch (error) { ElMessage.error(errorMessage(error)); }
}
async function remove(item: DatabaseAccount) {
  try { await manageDatabaseAccount(props.assetId, { action: 'delete', database: props.database, name: item.name, host: item.host }, 'DELETE'); await load(); }
  catch (error) { ElMessage.error(errorMessage(error)); }
}
</script>

<template>
  <el-dialog :model-value="modelValue" :close-on-click-modal="false" title="数据库账号管理" width="min(820px, 94vw)" @update:model-value="emit('update:modelValue', $event)">
    <div class="account-toolbar"><el-button type="primary" @click="openAccount()">新增账号</el-button><el-button @click="load">刷新</el-button></div>
    <el-table v-loading="loading" :data="accounts" height="360">
      <el-table-column prop="name" label="账号" min-width="180" /><el-table-column prop="host" label="Host" width="150" />
      <el-table-column label="角色" min-width="160"><template #default="scope">{{ scope.row.roles.join(', ') || '-' }}</template></el-table-column>
      <el-table-column label="权限" min-width="240"><template #default="scope">{{ scope.row.permissions.join(', ') || '-' }}</template></el-table-column>
      <el-table-column label="操作" width="170"><template #default="scope"><el-button text @click="openAccount(scope.row)">编辑</el-button><el-popconfirm title="确定删除该数据库账号吗？" @confirm="remove(scope.row)"><template #reference><el-button text type="danger" :disabled="scope.row.protected || scope.row.capabilities?.delete === false">删除</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <el-form v-if="formOpen" class="account-form" label-position="top">
      <div class="account-form-grid"><el-form-item label="账号"><el-input v-model="form.name" :disabled="!!editing" /></el-form-item><el-form-item label="Host"><el-input v-model="form.host" :disabled="!!editing" /></el-form-item><el-form-item :label="editing ? '新密码（留空不修改）' : '密码'"><el-input v-model="form.password" type="password" show-password /></el-form-item></div>
      <el-form-item v-if="['postgresql', 'kingbase', 'sqlserver'].includes(dbType)" label="Schema"><el-input v-model="form.schema" /></el-form-item>
      <el-form-item label="追加授权"><el-checkbox-group v-model="form.grants"><el-checkbox v-for="permission in privileges" :key="permission" :label="permission">{{ permission }}</el-checkbox></el-checkbox-group></el-form-item>
      <el-form-item v-if="editing" label="撤销权限"><el-checkbox-group v-model="form.revokes" :disabled="editing.protected"><el-checkbox v-for="permission in privileges" :key="permission" :label="permission">{{ permission }}</el-checkbox></el-checkbox-group></el-form-item>
      <el-form-item label="授予角色"><el-select v-model="form.addRoles" multiple :disabled="editing?.protected" style="width:100%"><el-option v-for="role in roleOptions" :key="JSON.stringify([role.name, role.host])" :label="role.host ? `${role.name}@${role.host}` : role.name" :value="JSON.stringify([role.name, role.host])" /></el-select></el-form-item>
      <el-form-item v-if="editing" label="撤销角色"><el-select v-model="form.removeRoles" multiple :disabled="editing.protected" style="width:100%"><el-option v-for="role in roleOptions" :key="JSON.stringify([role.name, role.host])" :label="role.host ? `${role.name}@${role.host}` : role.name" :value="JSON.stringify([role.name, role.host])" /></el-select></el-form-item>
      <el-button type="primary" @click="save">保存账号</el-button><el-button @click="formOpen = false; editing = null">取消</el-button>
    </el-form>
  </el-dialog>
</template>

<style scoped>
.account-toolbar{display:flex;gap:8px;margin-bottom:10px}.account-form{margin-top:16px;padding-top:14px;border-top:1px solid var(--el-border-color)}.account-form-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}@media(max-width:720px){.account-form-grid{grid-template-columns:1fr}}
</style>
