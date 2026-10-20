<script setup lang="ts">
defineProps<{ embedded?: boolean; modelValue: boolean; title: string; width?: string }>();
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>();
</script>
<template>
  <section v-if="embedded" class="database-editor-frame"><header>{{ title }}</header><div class="editor-body"><slot /></div><footer v-if="$slots.footer"><slot name="footer" /></footer></section>
  <el-dialog v-else :model-value="modelValue" :title="title" :width="width" :close-on-click-modal="false" @update:model-value="emit('update:modelValue', $event)"><slot /><template v-if="$slots.footer" #footer><slot name="footer" /></template></el-dialog>
</template>
<style scoped>
.database-editor-frame{display:flex;flex-direction:column;height:100%;min-height:0}.database-editor-frame>header{padding:14px 18px;border-bottom:1px solid var(--el-border-color);font-weight:600}.editor-body{flex:1;overflow:auto;padding:18px;min-height:0}.database-editor-frame>footer{padding:12px 18px;border-top:1px solid var(--el-border-color);text-align:right}
.database-editor-frame :deep(.el-input__wrapper),.database-editor-frame :deep(.el-select__wrapper),.database-editor-frame :deep(.el-textarea__inner){box-shadow:0 0 0 1px var(--el-border-color) inset!important;background:var(--el-fill-color-blank)!important}.database-editor-frame :deep(.el-input__wrapper:hover),.database-editor-frame :deep(.el-select__wrapper:hover),.database-editor-frame :deep(.el-textarea__inner:hover){box-shadow:0 0 0 1px var(--el-border-color-hover) inset!important}.database-editor-frame :deep(.el-input__wrapper.is-focus),.database-editor-frame :deep(.el-select__wrapper.is-focused),.database-editor-frame :deep(.el-textarea__inner:focus){box-shadow:0 0 0 1px var(--el-color-primary) inset!important}
</style>
