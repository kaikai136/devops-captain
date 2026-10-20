<script setup lang="ts">
import { Handle, Position } from '@vue-flow/core';
import { Table2 } from '@lucide/vue';
import { fieldHandle, type DiagramTableData } from '../utils/databaseDiagram';
defineProps<{ data: DiagramTableData; selected?: boolean }>();
</script>
<template>
  <article class="er-node" :class="{ selected }" :aria-label="`${data.name} 表结构`">
    <header class="er-node-header"><Table2 :size="16" /><strong :title="data.name">{{ data.name }}</strong><small>{{ data.fields.length }} 字段</small></header>
    <div v-for="field in data.fields" :key="field.name" class="er-field" :title="[field.name, field.type, field.comment].filter(Boolean).join(' · ')">
      <Handle v-if="data.referencedKeys.includes(field.name)" type="target" :position="Position.Left" :id="fieldHandle(field.name)" :connectable="false" />
      <span class="er-key" :class="{ primary: field.column_key === 'PRI' }">{{ field.column_key === 'PRI' ? 'PK' : data.foreignKeys.includes(field.name) ? 'FK' : '·' }}</span>
      <b>{{ field.name }}</b><small>{{ field.type }}</small>
      <Handle v-if="data.foreignKeys.includes(field.name)" type="source" :position="Position.Right" :id="fieldHandle(field.name)" :connectable="false" />
    </div>
  </article>
</template>
<style scoped>
.er-node{box-sizing:border-box;width:300px;border:1px solid var(--el-border-color);border-radius:8px;background:var(--el-bg-color);color:var(--el-text-color-primary);box-shadow:0 3px 12px #00000012}.er-node.selected{border-color:var(--el-color-primary);box-shadow:0 0 0 2px var(--el-color-primary-light-7)}.er-node-header{box-sizing:border-box;display:flex;align-items:center;gap:8px;height:44px;padding:0 12px;border-radius:7px 7px 0 0;background:var(--el-fill-color-light);border-bottom:2px solid var(--el-color-primary);cursor:grab}.er-node-header:active{cursor:grabbing}.er-node-header svg{flex:none;color:var(--el-color-primary)}.er-node-header strong{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.er-node-header small{margin-left:auto;flex:none;color:var(--el-text-color-secondary);font-size:11px}.er-field{position:relative;box-sizing:border-box;display:flex;align-items:center;gap:6px;height:28px;padding:0 10px;border-bottom:1px solid var(--el-border-color-lighter);font-size:12px}.er-field:last-child{border-bottom:0}.er-field b{font-weight:400;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.er-field>small{margin-left:auto;max-width:44%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--el-text-color-secondary)}.er-key{width:20px;flex:none;font-size:10px;font-weight:600;color:var(--el-color-primary)}.er-key.primary{color:var(--el-color-warning)}.er-field :deep(.vue-flow__handle){width:7px;height:7px;border:1px solid var(--el-bg-color);background:var(--el-color-primary);pointer-events:none}
</style>
