<script setup lang="ts">
import { computed, nextTick, reactive, ref } from 'vue';
import { Plus, Trash2, X } from '@lucide/vue';
import DatabaseBrandIcon from './DatabaseBrandIcon.vue';
import ConnectionFileField from './ConnectionFileField.vue';
import { createDatabaseAsset, updateDatabaseAsset, testDatabaseConnection, type DatabaseAsset, type ConnectionSecretKey } from '../api/databaseManagement';
import { connectionColors, environments, mysqlDraft, parameterLabels, sqlModes } from '../utils/mysqlConnection';
import { errorMessage } from '@shared/utils/errors';

const props = defineProps<{ asset?: DatabaseAsset | null; directoryId?: number | null; credentials: { id: number; name: string; username: string; password: string }[]; canTest: boolean; canSave: boolean }>();
const emit = defineEmits<{ close: []; saved: [asset: DatabaseAsset] }>();
const draft = mysqlDraft(props.asset, props.directoryId);
const form = reactive(draft.form);
const options = reactive(draft.options);
form.options = options;
const activeTab = ref('general');
const tabs = [{ id: 'general', label: '常规' }, { id: 'advanced', label: '高级' }, { id: 'parameters', label: '参数' }, { id: 'ssl', label: 'SSL' }];
const testing = ref(false);
const saving = ref(false);
const busy = computed(() => testing.value || saving.value);
const message = ref('');
const messageType = ref<'error' | 'success'>('error');
const errors = ref<Record<string, string>>({});
const credentialId = ref<number | null>(null);
const databases = ref<string[]>([]);
function suggestDatabases(query: string, done: (items: { value: string }[]) => void) {
  done(databases.value.filter(name => name.toLowerCase().includes(query.toLowerCase())).map(value => ({ value })));
}
const expiry = ref(options.expiresAt ? new Date(options.expiresAt) : null);
type ParameterRow = { key: string; value: string | number | boolean };
const parameters = ref<ParameterRow[]>(Object.entries(options.parameters).map(([key, value]) => ({ key, value: value! })));
const availableParameters = computed(() => Object.keys(parameterLabels).filter(key => !parameters.value.some(row => row.key === key)));
const sqlModeValues = (row: ParameterRow) => String(row.value || '').split(',').filter(Boolean);
function addParameter() { const key = availableParameters.value[0]; if (key) parameters.value.push({ key, value: key === 'autocommit' ? false : ['readTimeout', 'writeTimeout'].includes(key) ? 20 : '' }); }
function changeParameter(row: ParameterRow) { row.value = row.key === 'autocommit' ? false : ['readTimeout', 'writeTimeout'].includes(row.key) ? 20 : ''; }
function applyCredential(id: number | null) { const item = props.credentials.find(value => value.id === id); if (item) { form.username = item.username; form.password = item.password; options.authMethod = 'password'; } }
function fileName(key: ConnectionSecretKey) { const value = form.connectionSecrets?.[key]; return value === null ? undefined : typeof value === 'object' && value ? value.name : props.asset?.connectionSecretStatus?.[key]?.name; }
function hasSecret(key: ConnectionSecretKey) { const value = form.connectionSecrets?.[key]; return value === undefined ? Boolean(props.asset?.connectionSecretStatus?.[key]?.configured) : Boolean(value); }
function secretPlaceholder(key: ConnectionSecretKey) { return hasSecret(key) ? '已设置，留空保留' : '请输入'; }
function setSecret(key: ConnectionSecretKey, value: string | { name: string; content: string } | null) { if (value === '') delete form.connectionSecrets![key]; else form.connectionSecrets![key] = value; }
function showError(value: string) { messageType.value = 'error'; message.value = value; }
function serverError(error: unknown) {
  const value = errorMessage(error);
  if (/证书|SSL|CA|配对/.test(value)) activeTab.value = 'ssl';
  else if (/SSH/.test(value)) activeTab.value = 'advanced';
  else if (/参数|SQL 模式|时区/.test(value)) activeTab.value = 'parameters';
  showError(value);
}
async function validate() {
  const found: { tab: string; field: string; text: string }[] = [];
  const add = (tab: string, field: string, text: string) => found.push({ tab, field, text });
  if (!form.name.trim()) add('general', 'name', '请输入连接名称');
  if (!form.host || /[\s/\\@]/.test(form.host)) add('general', 'host', '请输入合法的主机名或 IP 地址');
  if (!Number.isInteger(form.port) || form.port < 1 || form.port > 65535) add('general', 'port', '端口范围为 1～65535');
  if (!form.username.trim()) add('general', 'username', '请输入用户');
  if (!Number.isInteger(options.connectTimeout) || options.connectTimeout < 1 || options.connectTimeout > 120) add('advanced', 'timeout', '连接超时范围为 1～120 秒');
  if (options.ssh.enabled) {
    if (!options.ssh.host || /[\s/\\@]/.test(options.ssh.host)) add('advanced', 'sshHost', '请输入 SSH 地址');
    if (!options.ssh.username.trim()) add('advanced', 'sshUser', '请输入 SSH 用户');
    if (!Number.isInteger(options.ssh.port) || options.ssh.port < 1 || options.ssh.port > 65535) add('advanced', 'sshPort', 'SSH 端口范围为 1～65535');
    if (!hasSecret(options.ssh.authMethod === 'password' ? 'sshPassword' : 'sshPrivateKey')) add('advanced', 'sshAuth', '请补全 SSH 认证材料');
  }
  parameters.value.forEach(row => {
    if (['readTimeout', 'writeTimeout'].includes(row.key) && (!Number.isInteger(row.value) || Number(row.value) < 1 || Number(row.value) > 600)) add('parameters', 'parameters', '超时参数范围为 1～600 秒');
    if (row.key === 'timeZone' && row.value && row.value !== 'SYSTEM' && !/^(?:[+-](?:0\d|1[0-3]):[0-5]\d|\+14:00)$/.test(String(row.value))) {
      try { new Intl.DateTimeFormat('en', { timeZone: String(row.value) }); }
      catch { add('parameters', 'parameters', '请输入 SYSTEM、UTC 偏移或合法时区名'); }
    }
  });
  if (options.ssl) {
    if (options.tls.mode !== 'require' && !hasSecret('sslCa')) add('ssl', 'sslCa', '验证模式必须选择 CA 证书');
    if (hasSecret('sslCert') !== hasSecret('sslKey')) add('ssl', 'sslCert', '客户端证书与私钥必须成对提供');
  }
  errors.value = Object.fromEntries(found.map(item => [item.field, item.text]));
  if (found.length) {
    activeTab.value = found[0].tab; showError(found[0].text); await nextTick();
    const element = document.querySelector<HTMLElement>(`.mysql-connection-dialog [data-field="${found[0].field}"]`);
    element?.scrollIntoView({ block: 'nearest' }); element?.querySelector<HTMLElement>('input,button')?.focus();
    return false;
  }
  return true;
}
function payload() {
  options.expiresAt = expiry.value ? new Date(expiry.value).toISOString() : null;
  options.parameters = Object.fromEntries(parameters.value.map(row => [row.key, row.value]));
  const value = JSON.parse(JSON.stringify(form));
  if (props.asset && !value.password) delete value.password;
  return value;
}
async function test() {
  if (busy.value || !props.canTest || !props.canSave || !await validate()) return;
  if (busy.value) return;
  testing.value = true; message.value = '';
  try { const result = await testDatabaseConnection({ ...payload(), ...(props.asset ? { assetId: props.asset.id } : {}) }); databases.value = result.databases; messageType.value = result.ok ? 'success' : 'error'; message.value = `${result.message} · ${result.elapsedMs} ms`; }
  catch (error) { serverError(error); }
  finally { testing.value = false; }
}
async function save() {
  if (busy.value || !props.canSave || !await validate()) return;
  if (busy.value) return;
  saving.value = true; message.value = '';
  try { const result = props.asset ? await updateDatabaseAsset(props.asset.id, payload()) : await createDatabaseAsset(payload()); emit('saved', result); }
  catch (error) { serverError(error); }
  finally { saving.value = false; }
}
</script>

<template>
  <el-dialog :model-value="true" class="mysql-connection-dialog" width="680px" align-center :close-on-click-modal="false" :close-on-press-escape="!busy" :show-close="!busy" @close="emit('close')">
    <template #header><div class="mysql-dialog-heading"><DatabaseBrandIcon db-type="mysql" :connected="true" /><span>{{ asset ? '编辑 MySQL 连接' : '新建 MySQL 连接' }}</span></div></template>
    <div class="mysql-dialog-tabs" role="tablist" aria-label="连接设置">
      <el-button v-for="tab in tabs" :id="`mysql-tab-${tab.id}`" :key="tab.id" role="tab" :aria-selected="activeTab === tab.id" :aria-controls="`mysql-panel-${tab.id}`" :class="{ selected: activeTab === tab.id }" @click="activeTab = tab.id">{{ tab.label }}</el-button>
    </div>
    <div class="mysql-dialog-scroll">
      <el-alert v-if="message" :title="message" :type="messageType" :closable="false" show-icon />
      <el-form label-position="top" :disabled="!canSave || busy" class="mysql-dialog-form" @submit.prevent>
        <section v-show="activeTab === 'general'" id="mysql-panel-general" class="mysql-form-grid" role="tabpanel" aria-labelledby="mysql-tab-general">
          <el-form-item label="颜色标签"><div class="mysql-colors"><el-button v-for="color in connectionColors" :key="color" circle :aria-label="`颜色 ${color}`" :aria-pressed="options.color === color" :class="{ chosen: options.color === color }" :style="{ '--connection-color': color }" @click="options.color = color" /><el-button circle aria-label="清除颜色" title="清除颜色" @click="options.color = ''"><X :size="13" /></el-button></div></el-form-item>
          <el-form-item label="环境"><div class="mysql-environment"><el-select v-model="options.environment" placeholder="无"><el-option label="无" value="" /><el-option v-for="(label, value) in environments" :key="value" :label="label" :value="value" /></el-select><el-checkbox v-model="options.readOnly">只读</el-checkbox></div></el-form-item>
          <el-form-item label="名称" :error="errors.name" data-field="name" required><el-input v-model="form.name" maxlength="160" placeholder="连接名称" /></el-form-item>
          <el-form-item label="主机" :error="errors.host" data-field="host" required><el-input v-model="form.host" placeholder="主机名 / IP 地址" /></el-form-item>
          <el-form-item label="用户" :error="errors.username" data-field="username" required><el-input v-model="form.username" maxlength="120" autocomplete="off" /></el-form-item>
          <el-form-item label="端口" :error="errors.port" data-field="port" required><el-input-number v-model="form.port" :min="1" :max="65535" controls-position="right" /></el-form-item>
          <el-form-item label="验证方式"><el-select v-model="options.authMethod"><el-option label="密码" value="password" /><el-option label="无密码" value="none" /></el-select></el-form-item>
          <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" :disabled="options.authMethod === 'none'" :placeholder="asset ? '留空保持原密码' : '请输入密码'" /></el-form-item>
          <el-form-item label="应用密钥" class="full"><el-select v-model="credentialId" clearable placeholder="可选：使用应用密钥填充用户和密码" @change="applyCredential"><el-option v-for="item in credentials" :key="item.id" :value="item.id" :label="item.name" /></el-select></el-form-item>
          <el-form-item label="备注" class="full"><el-input v-model="form.remark" type="textarea" :rows="2" resize="vertical" placeholder="可选" /></el-form-item>
        </section>
        <section v-show="activeTab === 'advanced'" id="mysql-panel-advanced" class="mysql-form-grid" role="tabpanel" aria-labelledby="mysql-tab-advanced">
          <el-form-item label="默认数据库"><el-autocomplete v-model="form.databaseName" :fetch-suggestions="suggestDatabases" clearable placeholder="输入数据库，或测试成功后选择" /></el-form-item>
          <el-form-item label="连接超时（秒）" data-field="timeout" :error="errors.timeout"><el-input-number v-model="options.connectTimeout" :min="1" :max="120" controls-position="right" /></el-form-item>
          <el-form-item label="编码"><el-select v-model="options.charset"><el-option label="自动（utf8mb4）" value="auto" /><el-option v-for="charset in ['utf8mb4', 'utf8', 'latin1', 'gbk', 'gb18030']" :key="charset" :label="charset" :value="charset" /></el-select></el-form-item>
          <el-form-item label="到期时间"><el-date-picker v-model="expiry" type="datetime" clearable placeholder="留空表示不过期" format="YYYY-MM-DD HH:mm:ss" /></el-form-item>
          <div class="mysql-section-title full"><span>SSH 跳板机</span><el-switch v-model="options.ssh.enabled" aria-label="启用 SSH" /></div>
          <template v-if="options.ssh.enabled">
            <p class="mysql-hint full">常规页的主机和端口为跳板机可访问的 MySQL 目标地址。</p>
            <el-form-item label="SSH 地址" data-field="sshHost" :error="errors.sshHost"><el-input v-model="options.ssh.host" /></el-form-item>
            <el-form-item label="SSH 端口" data-field="sshPort" :error="errors.sshPort"><el-input-number v-model="options.ssh.port" :min="1" :max="65535" controls-position="right" /></el-form-item>
            <el-form-item label="SSH 用户" data-field="sshUser" :error="errors.sshUser"><el-input v-model="options.ssh.username" /></el-form-item>
            <el-form-item label="SSH 验证方式"><el-select v-model="options.ssh.authMethod"><el-option label="密码" value="password" /><el-option label="私钥" value="privateKey" /></el-select></el-form-item>
            <el-form-item v-if="options.ssh.authMethod === 'password'" label="SSH 密码" class="full" data-field="sshAuth" :error="errors.sshAuth"><el-input :model-value="form.connectionSecrets?.sshPassword || ''" type="password" show-password :placeholder="secretPlaceholder('sshPassword')" @update:model-value="setSecret('sshPassword', $event)" /></el-form-item>
            <template v-else><el-form-item label="SSH 私钥" data-field="sshAuth" :error="errors.sshAuth"><ConnectionFileField label="SSH 私钥" :name="fileName('sshPrivateKey')" :disabled="!canSave || busy" @change="setSecret('sshPrivateKey', $event)" @error="showError" /></el-form-item><el-form-item label="私钥口令"><el-input :model-value="form.connectionSecrets?.sshKeyPassword || ''" type="password" show-password :placeholder="secretPlaceholder('sshKeyPassword')" @update:model-value="setSecret('sshKeyPassword', $event)" /><el-button v-if="hasSecret('sshKeyPassword')" text size="small" @click="setSecret('sshKeyPassword', null)">清除已保存口令</el-button></el-form-item></template>
          </template>
        </section>
        <section v-show="activeTab === 'parameters'" id="mysql-panel-parameters" role="tabpanel" aria-labelledby="mysql-tab-parameters" data-field="parameters">
          <div class="mysql-section-title"><span>连接参数</span><el-button :disabled="!availableParameters.length" size="small" @click="addParameter"><Plus :size="14" />添加参数</el-button></div>
          <p class="mysql-hint">读取 / 写入超时默认为 20 秒，自动提交默认关闭。未设置 SQL 模式与会话时区时沿用服务器值。</p>
          <div v-if="!parameters.length" class="mysql-parameter-empty">尚未添加参数，使用默认配置</div>
          <div v-for="(row, index) in parameters" :key="index" class="mysql-parameter-row">
            <el-select v-model="row.key" aria-label="参数名" @change="changeParameter(row)"><el-option v-for="(label, key) in parameterLabels" :key="key" :label="label" :value="key" :disabled="parameters.some(other => other !== row && other.key === key)" /></el-select>
            <el-input-number v-if="['readTimeout', 'writeTimeout'].includes(row.key)" v-model="row.value" aria-label="超时秒数" :min="1" :max="600" controls-position="right" />
            <el-switch v-else-if="row.key === 'autocommit'" v-model="row.value" aria-label="自动提交" />
            <el-select v-else-if="row.key === 'sqlMode'" :model-value="sqlModeValues(row)" multiple collapse-tags aria-label="SQL 模式" @update:model-value="row.value = $event.join(',')"><el-option v-for="mode in sqlModes" :key="mode" :value="mode" :label="mode" /></el-select>
            <el-input v-else v-model="row.value" aria-label="会话时区" placeholder="SYSTEM、+08:00、Asia/Shanghai" />
            <el-button text aria-label="删除参数" @click="parameters.splice(index, 1)"><Trash2 :size="15" /></el-button>
          </div>
          <p v-if="errors.parameters" class="mysql-error">{{ errors.parameters }}</p>
        </section>
        <section v-show="activeTab === 'ssl'" id="mysql-panel-ssl" class="mysql-form-grid" role="tabpanel" aria-labelledby="mysql-tab-ssl">
          <div class="mysql-section-title full"><span>SSL 加密连接</span><el-switch v-model="options.ssl" aria-label="启用 SSL" /></div>
          <el-form-item label="SSL 模式" class="full"><el-select v-model="options.tls.mode" :disabled="!options.ssl"><el-option label="Require（不验证证书）" value="require" /><el-option label="Verify CA（验证 CA 证书）" value="verify_ca" /><el-option label="Verify Identity（验证证书与主机名）" value="verify_identity" /></el-select></el-form-item>
          <el-form-item label="CA 证书" class="full" data-field="sslCa" :error="errors.sslCa"><ConnectionFileField label="CA 证书" :name="fileName('sslCa')" :disabled="!options.ssl || !canSave || busy" @change="setSecret('sslCa', $event)" @error="showError" /></el-form-item>
          <el-form-item label="客户端证书" data-field="sslCert" :error="errors.sslCert"><ConnectionFileField label="客户端证书" :name="fileName('sslCert')" :disabled="!options.ssl || !canSave || busy" @change="setSecret('sslCert', $event)" @error="showError" /></el-form-item>
          <el-form-item label="客户端私钥"><ConnectionFileField label="客户端私钥" :name="fileName('sslKey')" :disabled="!options.ssl || !canSave || busy" @change="setSecret('sslKey', $event)" @error="showError" /></el-form-item>
          <el-form-item label="私钥口令" class="full"><el-input :model-value="form.connectionSecrets?.sslKeyPassword || ''" :disabled="!options.ssl" type="password" show-password :placeholder="secretPlaceholder('sslKeyPassword')" @update:model-value="setSecret('sslKeyPassword', $event)" /><el-button v-if="hasSecret('sslKeyPassword')" text size="small" :disabled="!options.ssl" @click="setSecret('sslKeyPassword', null)">清除已保存口令</el-button></el-form-item>
          <p class="mysql-hint full">文件仅用于加密连接，每个文件最多 256KB。Verify Identity 使用真实 MySQL 主机名校验；通过 SSH 连接时同样适用。</p>
        </section>
      </el-form>
    </div>
    <template #footer><div class="mysql-dialog-footer"><el-button :loading="testing" :disabled="!canTest || !canSave || busy" @click="test">测试连接</el-button><div><el-button :disabled="busy" @click="emit('close')">取消</el-button><el-button type="primary" :loading="saving" :disabled="!canSave || busy" @click="save">保存</el-button></div></div></template>
  </el-dialog>
</template>

<style>
.el-dialog.mysql-connection-dialog{--el-dialog-padding-primary:0;width:min(680px,calc(100vw - 24px));max-height:calc(100dvh - 32px);padding:0!important;display:flex;flex-direction:column;border:1px solid var(--el-border-color);border-radius:7px;background:var(--el-fill-color-light);overflow:hidden;color:var(--el-text-color-primary)}
.mysql-connection-dialog .el-dialog__header{flex:none;padding:17px 22px!important;margin:0!important;border-bottom:1px solid var(--el-border-color-lighter);background:var(--el-fill-color-light)}
.mysql-dialog-heading{display:flex;align-items:center;gap:9px;font-size:16px;font-weight:600}.mysql-dialog-heading .db-brand-icon{width:23px;height:23px}
.mysql-connection-dialog .el-dialog__body{display:flex;flex-direction:column;min-height:0;padding:0!important;overflow:hidden;background:transparent}
.mysql-dialog-tabs{display:flex;justify-content:center;flex:none;gap:0;padding:12px 16px 0;background:var(--el-fill-color-light)}
.mysql-dialog-tabs .el-button{height:36px;min-width:82px;margin:0!important;border-radius:0;border:0;border-bottom:2px solid transparent;background:transparent;font-size:13px;font-weight:500;color:var(--el-text-color-secondary)}
.mysql-dialog-tabs .el-button.selected{color:var(--el-color-primary);border-bottom-color:var(--el-color-primary);background:var(--el-bg-color)}
.mysql-dialog-scroll{padding:20px 24px;min-height:0;overflow:auto;overscroll-behavior:contain;background:var(--el-bg-color);margin:0 14px;border:1px solid var(--el-border-color-lighter);border-radius:4px;scrollbar-gutter:stable}
.mysql-dialog-scroll>.el-alert{margin-bottom:16px;overflow-wrap:anywhere}.mysql-dialog-form{min-height:350px}.mysql-form-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);column-gap:22px;row-gap:0}.mysql-form-grid .full{grid-column:1/-1}.mysql-dialog-form .el-form-item{min-width:0;margin-bottom:17px}.mysql-dialog-form .el-form-item__label{font-size:13px;font-weight:500;line-height:20px;margin-bottom:6px;color:var(--el-text-color-regular)}
.mysql-dialog-form .el-input,.mysql-dialog-form .el-select,.mysql-dialog-form .el-input-number,.mysql-dialog-form .el-date-editor{width:100%;min-width:0}.mysql-dialog-form .el-input__wrapper,.mysql-dialog-form .el-select__wrapper{min-height:36px;box-sizing:border-box;border-radius:4px;background:var(--el-fill-color-blank);box-shadow:0 0 0 1px var(--el-border-color) inset!important}.mysql-dialog-form .el-input__wrapper:hover,.mysql-dialog-form .el-select__wrapper:hover{box-shadow:0 0 0 1px var(--el-border-color-hover) inset!important}.mysql-dialog-form .el-input__wrapper.is-focus,.mysql-dialog-form .el-select__wrapper.is-focused{box-shadow:0 0 0 1px var(--el-color-primary) inset!important}.mysql-dialog-form .el-textarea__inner{border-radius:4px;background:var(--el-fill-color-blank);box-shadow:0 0 0 1px var(--el-border-color) inset!important;font-size:13px}.mysql-dialog-form .el-textarea__inner:focus{box-shadow:0 0 0 1px var(--el-color-primary) inset!important}.mysql-dialog-form .el-input__inner{height:34px;font-size:13px}.mysql-dialog-form .el-input-number__decrease,.mysql-dialog-form .el-input-number__increase{background:var(--el-fill-color-light)}
.mysql-colors{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.mysql-colors .el-button{width:20px!important;height:20px!important;min-height:0;padding:0;margin:0!important;background:var(--connection-color,var(--el-fill-color-blank));border:1px solid var(--el-border-color);box-shadow:none!important}.mysql-colors .chosen{outline:2px solid var(--el-text-color-primary);outline-offset:2px}.mysql-environment{display:flex;align-items:center;gap:15px;width:100%;min-width:0}.mysql-environment .el-checkbox{margin:0;flex:none}.mysql-section-title{display:flex;align-items:center;justify-content:space-between;gap:12px;border-bottom:1px solid var(--el-border-color-lighter);padding-bottom:9px;margin-bottom:15px;font-weight:500;font-size:13px}.mysql-section-title .el-button{gap:4px;font-weight:400}.mysql-hint{margin:0 0 17px;color:var(--el-text-color-secondary);font-size:12px;line-height:1.7;overflow-wrap:anywhere}.mysql-parameter-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr) 30px;gap:10px;align-items:center;margin:12px 0}.mysql-parameter-row>.el-button{padding:0;margin:0}.mysql-parameter-empty{padding:45px 12px;text-align:center;border:1px dashed var(--el-border-color);border-radius:4px;font-size:13px;color:var(--el-text-color-secondary)}.mysql-error{font-size:12px;color:var(--el-color-danger)}
.mysql-dialog-form .el-autocomplete{width:100%;min-width:0}.mysql-dialog-form .el-date-editor.el-input{width:100%!important}
.mysql-connection-dialog .el-dialog__footer{flex:none;padding:15px 24px!important;background:var(--el-fill-color-light);border-top:0}.mysql-dialog-footer{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px}.mysql-dialog-footer>div{display:flex;gap:8px}.mysql-dialog-footer .el-button{margin:0;font-weight:500;min-height:34px}.mysql-dialog-footer .el-button--primary{background:var(--el-color-primary)!important;border-color:var(--el-color-primary)!important;color:var(--el-color-white)!important}
@media(max-width:640px){.el-dialog.mysql-connection-dialog{max-height:calc(100dvh - 20px);width:calc(100vw - 20px)}.mysql-connection-dialog .el-dialog__header{padding:15px 16px!important}.mysql-dialog-tabs{padding:8px 8px 0}.mysql-dialog-tabs .el-button{min-width:0;flex:1;padding:0 8px}.mysql-dialog-scroll{margin:0 8px;padding:18px 14px}.mysql-form-grid{grid-template-columns:minmax(0,1fr)}.mysql-connection-dialog .el-dialog__footer{padding:14px 16px!important}.mysql-dialog-form{min-height:280px}.mysql-parameter-row{grid-template-columns:minmax(0,1fr) 30px}.mysql-parameter-row>.el-select:first-child{grid-column:1}.mysql-parameter-row>:nth-child(2){grid-row:2;grid-column:1}.mysql-parameter-row>.el-button{grid-row:1/3;grid-column:2}.mysql-colors{gap:9px}}
</style>
