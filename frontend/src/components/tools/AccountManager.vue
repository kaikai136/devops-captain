<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { useAppContext } from '@app/context';
import { createHostCredential, deleteHostCredential, updateHostCredential } from '../../services/hostManagement';
import type { HostCredential } from '../../types';
import AppIcon from '@shared/components/AppIcon.vue';
import SystemSearchPanel from '@shared/components/SystemSearchPanel.vue';

interface CredentialForm {
  name: string;
  username: string;
  password: string;
  privateKeyName: string;
  privateKey: string;
  remark: string;
}

const {
  activeTool,
  hostCredentials,
  loadHostCredentials,
  replaceHostCredential,
  removeHostCredential,
  canUsePageAction,
  canUseAnyPageAction,
} = useAppContext();

const credentials = hostCredentials;
const search = ref('');
const isLoading = ref(false);
const message = ref('');
const dialog = ref<{ mode: 'create' | 'edit'; credentialId: number | null } | null>(null);
const confirmDelete = ref<HostCredential | null>(null);
const form = ref<CredentialForm>(emptyForm());
const fullscreen = ref(false);

const filteredCredentials = computed(() => {
  const query = search.value.trim().toLowerCase();
  return credentials.value.filter((item) =>
    !query || [item.name, item.username, item.remark].filter(Boolean).some((value) => String(value).toLowerCase().includes(query)),
  );
});

const stats = computed(() => ({
  total: credentials.value.length,
  withPassword: credentials.value.filter((item) => item.password).length,
  withKey: credentials.value.filter((item) => item.privateKey).length,
}));

onMounted(loadCredentials);

async function loadCredentials() {
  isLoading.value = true;
  message.value = '';
  try {
    await loadHostCredentials();
  } catch (error) {
    message.value = (error as Error).message;
  } finally {
    isLoading.value = false;
  }
}

function openCreateDialog() {
  form.value = emptyForm();
  dialog.value = { mode: 'create', credentialId: null };
}

function openEditDialog(credential: HostCredential) {
  form.value = {
    name: credential.name,
    username: credential.username,
    password: credential.password,
    privateKeyName: credential.privateKeyName,
    privateKey: credential.privateKey,
    remark: credential.remark,
  };
  dialog.value = { mode: 'edit', credentialId: credential.id };
}

async function saveCredential() {
  message.value = '';
  const payload = {
    name: form.value.name.trim(),
    username: form.value.username.trim(),
    password: form.value.password.trim(),
    privateKeyName: form.value.privateKeyName.trim(),
    privateKey: form.value.privateKey.trim(),
    remark: form.value.remark.trim(),
  };

  if (!payload.name || !payload.username) {
    message.value = '请输入账号名称和用户';
    return;
  }

  try {
    const saved =
      dialog.value?.mode === 'edit' && dialog.value.credentialId
        ? await updateHostCredential(dialog.value.credentialId, payload)
        : await createHostCredential(payload);
    replaceHostCredential(saved);
    dialog.value = null;
  } catch (error) {
    message.value = (error as Error).message;
  }
}

async function uploadPrivateKey(uploadFile: { raw?: File }) {
  const file = uploadFile.raw;
  if (!file) return;
  form.value.privateKeyName = file.name;
  form.value.privateKey = await file.text();
}

async function deleteCredential() {
  if (!confirmDelete.value) return;
  message.value = '';
  try {
    const targetId = confirmDelete.value.id;
    await deleteHostCredential(targetId);
    removeHostCredential(targetId);
    confirmDelete.value = null;
  } catch (error) {
    message.value = (error as Error).message;
  }
}

function emptyForm(): CredentialForm {
  return {
    name: '',
    username: '',
    password: '',
    privateKeyName: '',
    privateKey: '',
    remark: '',
  };
}
</script>

<template>
  <section v-if="activeTool === 'accounts'" class="account-page app-management-page" :class="{ fullscreen }">
    <template v-if="canUseAnyPageAction('accounts', ['create', 'edit', 'delete'])">
    <SystemSearchPanel>
      <div class="account-toolbar">
        <el-input v-model="search" placeholder="输入账号名称/用户/备注搜索" class="account-toolbar-search" clearable />
        <div class="account-toolbar-actions">
          <el-button v-if="canUsePageAction('accounts', 'create')" type="primary" @click="openCreateDialog"><AppIcon name="plus" :size="16" />新增账号</el-button>
          <el-button title="刷新" aria-label="刷新" @click="loadCredentials"><AppIcon name="refresh" :size="16" /></el-button>
          <el-button :title="fullscreen ? '退出全屏' : '全屏'" :aria-label="fullscreen ? '退出全屏' : '全屏'" @click="fullscreen = !fullscreen">
            <AppIcon :name="fullscreen ? 'minimize' : 'maximize'" :size="18" />
          </el-button>
        </div>
      </div>
    </SystemSearchPanel>
    <article class="panel account-panel app-management-card">
      <div class="app-management-heading account-list-heading">
        <div><h2>账号管理</h2><span>共 {{ stats.total }} 个账号</span></div>
      </div>

      <div class="account-stats-line">
        <span>共 {{ stats.total }} 个账号</span>
        <span>密码 {{ stats.withPassword }}</span>
        <span>密钥 {{ stats.withKey }}</span>
        <span v-if="isLoading">加载中</span>
      </div>
      <p v-if="message" class="account-message">{{ message }}</p>

      <div class="account-table-wrap app-data-table-wrap">
        <el-table :data="filteredCredentials" row-key="id" class="account-table app-data-table" empty-text="没有匹配的账号">
          <el-table-column label="账号名称" min-width="150">
            <template #default="{ row }">
              <div class="account-name">
                <strong>{{ row.name }}</strong>
                <span>ID {{ row.id }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="username" label="用户" min-width="120" />
          <el-table-column label="密码" min-width="100">
            <template #default="{ row }">
              <el-tag :type="row.password ? 'success' : 'warning'" size="small" effect="dark">{{ row.password ? '已保存' : '未设置' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="独立密钥" min-width="150">
            <template #default="{ row }">
              <el-tag :type="row.privateKey ? 'primary' : 'info'" size="small" effect="dark">{{ row.privateKeyName || '未上传' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="170">
            <template #default="{ row }">{{ row.remark || '无备注' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <div class="account-actions">
                <el-button v-if="canUsePageAction('accounts', 'edit')" type="primary" size="small" @click="openEditDialog(row)">编辑</el-button>
                <el-button v-if="canUsePageAction('accounts', 'delete')" type="danger" size="small" @click="confirmDelete = row">删除</el-button>
                <span v-if="!canUseAnyPageAction('accounts', ['edit', 'delete'])" class="permission-placeholder">-</span>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </article>
    </template>
    <div v-else class="permission-empty">暂无可用功能</div>

    <el-dialog
      :model-value="dialog !== null"
      class="account-popup-dialog"
      :title="dialog?.mode === 'edit' ? '编辑账号' : '新增账号'"
      width="560px"
      :close-on-click-modal="false"
      @update:model-value="(visible) => { if (!visible) dialog = null; }"
    >
      <el-form :model="form" label-position="left" label-width="92px" class="popup-body popup-form-grid account-popup-form">
        <el-form-item label="账号名称" required>
          <el-input v-model="form.name" autofocus />
        </el-form-item>
        <el-form-item label="用户" required>
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="独立密钥">
          <div class="account-key-upload">
            <el-upload :auto-upload="false" :show-file-list="false" :on-change="uploadPrivateKey">
              <el-button>点击上传</el-button>
            </el-upload>
            <em>{{ form.privateKeyName || '未上传独立密钥' }}</em>
          </div>
        </el-form-item>
        <el-form-item label="备注信息">
          <el-input v-model="form.remark" type="textarea" :rows="3" />
        </el-form-item>
        <p v-if="message" class="account-message">{{ message }}</p>
      </el-form>
      <template #footer>
        <div class="popup-actions">
          <el-button @click="dialog = null">取消</el-button>
          <el-button type="primary" @click="saveCredential">保存</el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      :model-value="confirmDelete !== null"
      class="account-popup-dialog account-confirm-popup"
      title="删除账号"
      width="420px"
      :close-on-click-modal="false"
      @update:model-value="(visible) => { if (!visible) confirmDelete = null; }"
    >
      <p class="popup-body">确定删除账号「{{ confirmDelete?.name }}」吗？</p>
      <template #footer>
        <div class="popup-actions">
          <el-button @click="confirmDelete = null">取消</el-button>
          <el-button type="danger" @click="deleteCredential">确定删除</el-button>
        </div>
      </template>
    </el-dialog>
  </section>
</template>
