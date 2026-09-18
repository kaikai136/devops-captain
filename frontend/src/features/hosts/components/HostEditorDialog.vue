<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from 'reka-ui';
import { computed, ref } from 'vue';

import type { HostCredential } from '@features/hosts/types';
import type { HostFormErrors, ManagedHostForm } from '@features/hosts/composables/useHostEditor';
import type { HostGroupRoot } from '@features/hosts/composables/useHostGroups';
import type { FlatHostGroup } from '@features/hosts/utils/groups';
import AppIcon from '@shared/components/AppIcon.vue';
import CredentialSelector from './CredentialSelector.vue';

const props = defineProps<{
  dialog: { mode: 'create' | 'edit'; hostId: number | null } | null;
  form: ManagedHostForm;
  errors: HostFormErrors;
  root: HostGroupRoot;
  groups: FlatHostGroup[];
  credentials: HostCredential[];
}>();

const emit = defineEmits<{
  (event: 'close'): void;
  (event: 'submit'): void;
  <Key extends keyof ManagedHostForm>(
    event: 'update-form-field',
    field: Key,
    value: ManagedHostForm[Key],
  ): void;
  (event: 'apply-credential', payload: number | null): void;
  (event: 'upload-private-key', payload: Event): void;
}>();

function fieldModel<Key extends keyof ManagedHostForm>(field: Key) {
  return computed({
    get: () => props.form[field],
    set: (value: ManagedHostForm[Key]) => emit('update-form-field', field, value),
  });
}

const group = fieldModel('group');
const name = fieldModel('name');
const privateIp = fieldModel('privateIp');
const os = fieldModel('os');
const port = fieldModel('port');
const loginUser = fieldModel('loginUser');
const loginPassword = fieldModel('loginPassword');
const remark = fieldModel('remark');
const privateKeyInput = ref<HTMLInputElement | null>(null);
const isEditing = computed(() => props.dialog?.mode === 'edit');
const dialogTitle = computed(() => (isEditing.value ? '编辑主机' : '新增主机'));
const dialogDescription = computed(() => (
  isEditing.value ? '更新主机连接信息与登录凭据。' : '填写主机信息，将新节点加入资产列表。'
));

function triggerPrivateKeyUpload() {
  privateKeyInput.value?.click();
}

function handleOpenChange(open: boolean) {
  if (!open) emit('close');
}
</script>

<template>
  <DialogRoot v-if="props.dialog" :open="Boolean(props.dialog)" @update:open="handleOpenChange">
    <DialogPortal disabled>
      <DialogOverlay class="host-editor-overlay" />
      <DialogContent
        class="host-editor-dialog"
        aria-describedby="host-editor-description"
        @interact-outside.prevent
      >
        <header class="host-editor-header">
          <div class="host-editor-heading">
            <span class="host-editor-heading-icon">
              <AppIcon name="server" :size="21" />
            </span>
            <div>
              <DialogTitle class="host-editor-title">{{ dialogTitle }}</DialogTitle>
              <DialogDescription id="host-editor-description" class="host-editor-description">
                {{ dialogDescription }}
              </DialogDescription>
            </div>
          </div>
          <DialogClose class="host-editor-icon-button" aria-label="关闭弹窗">
            <AppIcon name="x" :size="18" />
          </DialogClose>
        </header>

        <form
          id="host-editor-form"
          class="host-form-modal host-editor-form popup-body popup-form-grid"
          @submit.prevent="emit('submit')"
        >
          <section class="host-editor-section">
            <div class="host-editor-section-head">
              <span class="host-editor-section-icon">
                <AppIcon name="network" :size="17" />
              </span>
              <div>
                <h3>基础信息</h3>
                <p>配置主机归属、地址与连接端口。</p>
              </div>
            </div>

            <div class="host-editor-section-grid">
              <div class="host-horizontal-field required host-editor-span-2">
                <span>主机分组</span>
                <el-select v-model="group" :class="{ invalid: props.errors.group }" placeholder="请选择主机分组" :teleported="false">
                  <el-option disabled :value="null" :label="props.root.label" />
                  <el-option
                    v-for="hostGroup in props.groups"
                    :key="hostGroup.key"
                    :value="hostGroup.key"
                    :label="`${'　'.repeat(hostGroup.level)}${hostGroup.label}`"
                  />
                </el-select>
                <p v-if="props.errors.group" class="host-field-error">{{ props.errors.group }}</p>
              </div>
              <label class="host-horizontal-field required">
                <span>节点名称</span>
                <el-input v-model="name" :class="{ invalid: props.errors.name }" placeholder="例如：生产环境 Web-01" autofocus />
                <p v-if="props.errors.name" class="host-field-error">{{ props.errors.name }}</p>
              </label>
              <label class="host-horizontal-field required">
                <span>主机 IP</span>
                <el-input v-model="privateIp" :class="{ invalid: props.errors.privateIp }" placeholder="例如：192.168.1.10" />
                <p v-if="props.errors.privateIp" class="host-field-error">{{ props.errors.privateIp }}</p>
              </label>
              <div class="host-horizontal-field required">
                <span>平台类型</span>
                <el-select v-model="os" :class="{ invalid: props.errors.os }" placeholder="请选择平台类型" :teleported="false">
                  <el-option disabled value="" label="请选择平台类型" />
                  <el-option value="centos" label="Linux" />
                  <el-option value="windows" label="Windows" />
                </el-select>
                <p v-if="props.errors.os" class="host-field-error">{{ props.errors.os }}</p>
              </div>
              <label class="host-horizontal-field">
                <span>连接端口</span>
                <el-input-number v-model="port" :min="1" :max="65535" :class="{ invalid: props.errors.port }" controls-position="right" />
                <p v-if="props.errors.port" class="host-field-error">{{ props.errors.port }}</p>
              </label>
            </div>
          </section>

          <section class="host-editor-section">
            <div class="host-editor-section-head">
              <span class="host-editor-section-icon">
                <AppIcon name="key" :size="17" />
              </span>
              <div>
                <h3>登录凭据</h3>
                <p>选择已有账号，或手动填写本次连接信息。</p>
              </div>
            </div>

            <div class="host-editor-section-grid">
              <div class="host-horizontal-field host-editor-span-2">
                <span>凭据账号</span>
                <CredentialSelector
                  :model-value="props.form.credential"
                  :credentials="props.credentials"
                  @update:model-value="emit('update-form-field', 'credential', $event)"
                  @change="emit('apply-credential', $event)"
                />
              </div>
              <label class="host-horizontal-field">
                <span>登录用户</span>
                <el-input v-model="loginUser" placeholder="请输入用户名" />
              </label>
              <label class="host-horizontal-field">
                <span>登录密码</span>
                <el-input v-model="loginPassword" type="password" autocomplete="new-password" placeholder="请输入密码" show-password />
              </label>
              <div class="host-horizontal-field host-editor-span-2">
                <span>独立密钥</span>
                <div class="host-key-upload">
                  <input ref="privateKeyInput" hidden type="file" @change="emit('upload-private-key', $event)" />
                  <span class="host-key-upload-icon">
                    <AppIcon name="key" :size="19" />
                  </span>
                  <div class="host-key-upload-copy">
                    <strong>{{ props.form.privateKeyName || '使用全局默认密钥' }}</strong>
                    <em>{{ props.form.privateKeyName ? '已选择独立私钥，将优先用于本主机。' : '上传后将优先使用独立私钥连接此主机。' }}</em>
                  </div>
                  <el-button class="host-editor-button host-editor-button-outline host-key-button" native-type="button" @click="triggerPrivateKeyUpload">
                    <AppIcon name="upload" :size="16" />
                    选择文件
                  </el-button>
                </div>
              </div>
              <label class="host-horizontal-field host-editor-span-2">
                <span>备注信息</span>
                <el-input v-model="remark" type="textarea" :rows="3" placeholder="补充主机用途、环境或维护说明" />
              </label>
            </div>
          </section>
        </form>

        <footer class="host-form-actions host-editor-actions popup-footer popup-actions">
          <DialogClose as-child>
            <el-button class="host-editor-button host-editor-button-outline" native-type="button">取消</el-button>
          </DialogClose>
          <el-button form="host-editor-form" class="host-editor-button host-editor-button-primary" native-type="submit">
            {{ isEditing ? '保存修改' : '新增主机' }}
          </el-button>
        </footer>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
