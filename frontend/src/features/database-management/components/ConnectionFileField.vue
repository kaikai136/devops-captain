<script setup lang="ts">
import { ref } from 'vue';
import { FileKey2, Upload, X } from '@lucide/vue';
const props = defineProps<{ label: string; name?: string; disabled?: boolean }>();
const emit = defineEmits<{ change: [value: { name: string; content: string } | null]; error: [message: string] }>();
const input = ref<HTMLInputElement | null>(null);
async function choose(event: Event) {
  const element = event.target as HTMLInputElement;
  const file = element.files?.[0];
  element.value = '';
  if (!file || props.disabled) return;
  if (file.size > 256 * 1024) { emit('error', '每个文件最多 256KB'); return; }
  try {
    const content = await file.text();
    if (props.disabled) return;
    if (!/-----BEGIN (?:[A-Z0-9 ]+)?(?:CERTIFICATE|PRIVATE KEY)-----/.test(content)) { emit('error', '请选择 PEM 或 OpenSSH 格式的证书 / 私钥'); return; }
    emit('change', { name: file.name, content });
  } catch {
    emit('error', '无法读取文件，请重新选择');
  }
}
</script>
<template>
  <div class="connection-file">
    <input ref="input" type="file" accept=".pem,.crt,.cer,.key,.pub" hidden :disabled="disabled" :aria-label="label" @change="choose" />
    <div class="connection-file-name"><FileKey2 :size="15" /><span :title="name">{{ name || '未选择文件' }}</span></div>
    <el-button :disabled="disabled" size="small" :aria-label="`${name ? '替换' : '选择'}${label}`" @click="input?.click()"><Upload :size="13" />{{ name ? '替换' : '选择' }}</el-button>
    <el-button v-if="name" :disabled="disabled" size="small" text :aria-label="`移除${label}`" @click="emit('change', null)"><X :size="14" /></el-button>
  </div>
</template>
<style scoped>
.connection-file{display:flex;align-items:center;gap:6px;min-width:0;width:100%;min-height:36px;padding:4px 7px;border:1px solid var(--el-border-color);border-radius:4px;background:var(--el-fill-color-blank);box-sizing:border-box}
.connection-file-name{display:flex;align-items:center;gap:6px;min-width:0;flex:1;color:var(--el-text-color-secondary);font-size:12px}.connection-file-name span{overflow:hidden;white-space:nowrap;text-overflow:ellipsis}.connection-file-name svg{flex:none}.connection-file :deep(.el-button){margin:0;gap:4px;padding:4px 7px}
</style>
