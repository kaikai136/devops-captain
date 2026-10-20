<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue';
import { X } from '@lucide/vue';
import DatabaseBrandIcon from './DatabaseBrandIcon.vue';
import { testDatabaseConnection, type DatabaseAsset, type DatabaseAssetPayload, type DatabaseType } from '../api/databaseManagement';
import { connectionColors, environments } from '../utils/mysqlConnection';
import { useApplicationKeyChoices } from '../composables/useApplicationKeyChoices';
import { errorMessage } from '@shared/utils/errors';

const props = defineProps<{ asset?: DatabaseAsset | null; modelValue: DatabaseAssetPayload; type?: DatabaseType; canTest: boolean; canSave: boolean; files?: string[] }>();
const emit = defineEmits<{ close: []; save: [payload: DatabaseAssetPayload]; tested: [result: { ok: boolean; message: string } ] }>();
const form = reactive(props.modelValue);
const options = reactive(form.options || {});
form.options = options;
const activeTab = ref('general');
const testing = ref(false);
const message = ref('');
const messageType = ref<'success' | 'error'>('error');
const errors = reactive<Record<string, string>>({});
const { canUseKeys, keyChoices, selectedKey, loadingKeys, keyError, loadKeys } = useApplicationKeyChoices(() => props.asset || null, computed({ get: () => form.applicationKeyId ?? null, set: value => { form.applicationKeyId = value; } }));
const kind = computed(() => form.dbType);
const label = computed(() => props.type?.label || kind.value);
const tabs = computed(() => kind.value === 'sqlite' || kind.value === 'redis' ? ['general', 'advanced', 'parameters'] : ['general', 'advanced', 'parameters', 'ssl']);
const tabLabels: Record<string, string> = { general: '常规', advanced: '高级', parameters: '参数', ssl: 'SSL' };
const supports = (field: string) => props.type?.fields?.includes(field) || false;
const isSqlite = computed(() => kind.value === 'sqlite');
const isRedis = computed(() => kind.value === 'redis');
const needsDatabase = computed(() => !isRedis.value && !isSqlite.value && !['clickhouse'].includes(kind.value));
const needsPassword = computed(() => options.authMethod !== 'none' && options.authMethod !== 'applicationKey');
const authOptions = computed(() => isRedis.value ? [{ label: '密码', value: 'password' }, { label: '无密码', value: 'none' }, { label: '应用密钥', value: 'applicationKey' }] : [{ label: '用户名密码', value: 'password' }, { label: '无密码', value: 'none' }, { label: '应用密钥', value: 'applicationKey' }]);
watch(() => props.modelValue, value => { Object.assign(form, value); Object.assign(options, value.options || {}); }, { deep: true });
watch(() => kind.value, () => { if (!options.authMethod) options.authMethod = 'password'; });
function addError(field: string, text: string) { errors[field] = text; }
function validate() {
  Object.keys(errors).forEach(key => delete errors[key]);
  if (!String(form.name || '').trim()) addError('name', '名称不能为空');
  if (!isSqlite.value && (!String(form.host || '').trim() || /[\s/\\@]/.test(String(form.host)))) addError('host', '请输入合法的主机地址');
  if (!isSqlite.value && (!Number.isInteger(form.port) || form.port < 1 || form.port > 65535)) addError('port', '端口范围为 1-65535');
  if (isSqlite.value && !String(options.file || '').trim()) addError('file', '请选择文件');
  if (options.authMethod === 'applicationKey') { if (!form.applicationKeyId) addError('applicationKey', '请选择应用密钥'); else if (!isRedis.value && !selectedKey.value?.username?.trim()) addError('applicationKey', '应用密钥缺少用户名'); }
  else if (!isSqlite.value && !isRedis.value && !String(form.username || '').trim()) addError('username', '用户不能为空');
  if (needsPassword.value && !props.asset && !String(form.password || '').trim()) addError('password', '密码不能为空');
  if (kind.value === 'oracle' && !String(options.sid || options.service || '').trim()) addError('service', 'SID 或 Service Name 不能为空');
  return !Object.keys(errors).length;
}
function payload(): DatabaseAssetPayload {
  const value = JSON.parse(JSON.stringify(form)) as DatabaseAssetPayload;
  if (options.authMethod === 'applicationKey') { value.username = ''; delete value.password; }
  else value.applicationKeyId = null;
  if (kind.value !== 'mysql') {
    delete value.options.parametersText;
    delete value.options.charset;
    delete value.options.tlsMode;
  }
  if (props.asset && !value.password) delete value.password;
  return value;
}
async function test() {
  if (testing.value || !props.canTest || !validate()) return;
  testing.value = true; message.value = '';
  try { const result = await testDatabaseConnection({ ...payload(), ...(props.asset ? { assetId: props.asset.id } : {}) }); messageType.value = result.ok ? 'success' : 'error'; message.value = `${result.message}${result.elapsedMs ? ` · ${result.elapsedMs} ms` : ''}`; emit('tested', result); }
  catch (error) { messageType.value = 'error'; message.value = errorMessage(error); }
  finally { testing.value = false; }
}
function save() { if (testing.value || !props.canSave || !validate()) return; emit('save', payload()); }
</script>

<template>
  <el-dialog :model-value="true" class="mysql-connection-dialog" width="min(900px, calc(100vw - 32px))" :close-on-click-modal="false" :close-on-press-escape="!testing" :show-close="!testing" align-center lock-scroll @close="emit('close')">
    <template #header><div class="mysql-dialog-heading"><DatabaseBrandIcon :db-type="kind" :connected="true" /><span>{{ asset ? `编辑 ${label} 连接` : `新建 ${label} 连接` }}</span></div></template>
    <div class="mysql-dialog-tabs" role="tablist"><el-button v-for="tab in tabs" :key="tab" type="button" :class="{ selected: activeTab === tab }" @click="activeTab = tab">{{ tabLabels[tab] }}</el-button></div>
    <div class="mysql-dialog-scroll">
      <el-alert v-if="message" :title="message" :type="messageType" :closable="false" show-icon />
      <el-form label-position="top" class="mysql-dialog-form" :disabled="testing || !canSave" @submit.prevent>
        <section v-show="activeTab === 'general'" class="mysql-form-grid">
          <el-form-item label="颜色标签" class="full"><div class="mysql-colors"><el-button v-for="color in connectionColors" :key="color" circle :class="{ chosen: options.color === color }" :style="{ '--connection-color': color }" @click="options.color = color" /><el-button circle aria-label="????" @click="options.color = ''"><X :size="13" /></el-button></div></el-form-item>
          <el-form-item label="环境"><div class="mysql-environment"><el-select v-model="options.environment"><el-option label="无" value="" /><el-option v-for="(name, value) in environments" :key="value" :label="name" :value="value" /></el-select><el-checkbox v-model="options.readOnly">只读模式</el-checkbox></div></el-form-item>
          <el-form-item label="名称" required :error="errors.name"><el-input v-model="form.name" maxlength="160" /></el-form-item>
          <el-form-item v-if="!isSqlite" label="主机" required :error="errors.host"><el-input v-model="form.host" placeholder="localhost" /></el-form-item>
          <el-form-item v-if="isSqlite" label="数据源"><el-select v-model="options.source"><el-option label="文件" value="file" /><el-option label="内存" value="memory" /></el-select></el-form-item>
          <el-form-item v-if="isSqlite" label="文件" required :error="errors.file"><el-select v-model="options.file" filterable><el-option v-for="file in files || []" :key="file" :label="file" :value="file" /></el-select></el-form-item>
          <el-form-item v-if="!isSqlite" label="端口" required :error="errors.port"><el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" /></el-form-item>
          <el-form-item v-if="!isSqlite" label="认证方式"><el-select v-model="options.authMethod" @visible-change="$event && loadKeys()"><el-option v-for="item in authOptions" :key="item.value" :label="item.label" :value="item.value" /></el-select></el-form-item>
          <el-form-item v-if="!isSqlite && options.authMethod === 'applicationKey'" label="应用密钥" required :error="errors.applicationKey"><el-select v-model="form.applicationKeyId" filterable :loading="loadingKeys" :disabled="!canUseKeys"><el-option v-for="key in keyChoices" :key="key.id" :label="key.name" :value="key.id" :disabled="!isRedis && !key.username.trim()" /></el-select><small v-if="keyError">{{ keyError }}</small></el-form-item>
          <el-form-item v-if="!isSqlite" label="用户" :error="errors.username"><el-input v-if="options.authMethod !== 'applicationKey'" v-model="form.username" /><el-input v-else :model-value="selectedKey?.username || ''" readonly /></el-form-item>
          <el-form-item v-if="!isSqlite && options.authMethod !== 'applicationKey'" label="密码" :error="errors.password"><el-input v-model="form.password" type="password" show-password :placeholder="asset ? '留空保持原密码' : ''" /></el-form-item>
          <el-form-item v-if="needsDatabase" label="默认数据库"><el-input v-model="form.databaseName" /></el-form-item>
          <el-form-item v-if="supports('schema')" label="默认 Schema"><el-input v-model="options.schema" /></el-form-item>
          <el-form-item v-if="supports('instance')" label="实例名"><el-input v-model="options.instance" placeholder="例如：SQLEXPRESS" /></el-form-item>
          <el-form-item v-if="supports('service') || supports('sid')" label="SID / Service Name" :error="errors.service"><el-input v-model="options.service" placeholder="例如：XE、ORCL" /></el-form-item>
          <el-form-item label="备注" class="full"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
        </section>
        <section v-show="activeTab === 'advanced'" class="mysql-form-grid">
          <el-form-item label="连接超时（秒）"><el-input-number v-model="options.connectTimeout" :min="1" :max="120" controls-position="right" /></el-form-item>
          <el-form-item v-if="isRedis" label="Redis DB 编号"><el-input-number v-model="options.db" :min="0" :max="255" controls-position="right" /></el-form-item>
          <el-form-item v-if="isSqlite" label="附加数据库"><el-input v-model="options.attachDatabase" /></el-form-item>
          <el-form-item v-if="kind === 'sqlserver'" label="认证方式"><el-select v-model="options.authMode"><el-option label="SQL Server认证" value="sql" /><el-option label="Windows认证" value="windows" /></el-select></el-form-item>
          <el-form-item v-if="kind === 'clickhouse'" label="HTTPS"><el-switch v-model="options.https" /></el-form-item>
        </section>
        <section v-show="activeTab === 'parameters'" class="mysql-form-grid">
          <el-form-item label="字符集"><el-input v-model="options.charset" placeholder="auto" /></el-form-item>
          <el-form-item label="连接参数" class="full"><el-input v-model="options.parametersText" placeholder="key=value;key=value" /></el-form-item>
        </section>
        <section v-show="activeTab === 'ssl'" class="mysql-form-grid">
          <el-form-item label="启用 SSL"><el-switch v-model="options.ssl" /></el-form-item>
          <el-form-item label="TLS 模式"><el-select v-model="options.tlsMode"><el-option label="Require" value="require" /><el-option label="Verify CA" value="verify_ca" /><el-option label="Verify Identity" value="verify_identity" /></el-select></el-form-item>
        </section>
      </el-form>
    </div>
    <template #footer><div class="mysql-dialog-footer"><el-button text :disabled="testing || !canTest" @click="test">测试连接</el-button><div><el-button :disabled="testing" @click="emit('close')">取消</el-button><el-button type="primary" :loading="testing" :disabled="!canSave" @click="save">保存</el-button></div></div></template>
  </el-dialog>
</template>


