<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';
import { Database, DatabaseZap, List as ListIcon, X } from '@lucide/vue';

export interface DatabaseWorkspaceTab {
  id: string;
  kind: 'list' | 'asset';
  label: string;
  assetId?: number;
  dbType?: string;
  sticky?: boolean;
}

type ContextAction = 'close' | 'close-others' | 'close-all' | 'copy';

const props = defineProps<{
  modelValue: string;
  items: DatabaseWorkspaceTab[];
}>();

const emit = defineEmits<{
  (event: 'update:modelValue', id: string): void;
  (event: 'close', id: string): void;
  (event: 'reorder', payload: { id: string; beforeId: string }): void;
  (event: 'context-action', payload: { action: ContextAction; id: string }): void;
}>();

const draggedId = ref('');
const context = ref<{ id: string; x: number; y: number } | null>(null);

function selectTab(id: string) {
  emit('update:modelValue', id);
  context.value = null;
}

function startDrag(event: DragEvent, id: string) {
  const item = props.items.find(tab => tab.id === id);
  if (!item || item.sticky) return;
  draggedId.value = id;
  event.dataTransfer?.setData('text/plain', id);
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
}

function dropTab(event: DragEvent, beforeId: string) {
  event.preventDefault();
  const sourceId = draggedId.value || event.dataTransfer?.getData('text/plain') || '';
  const target = props.items.find(tab => tab.id === beforeId);
  if (!sourceId || sourceId === beforeId || target?.sticky) return;
  emit('reorder', { id: sourceId, beforeId });
  draggedId.value = '';
}

function openContext(event: MouseEvent, item: DatabaseWorkspaceTab) {
  if (item.sticky) return;
  context.value = { id: item.id, x: event.clientX, y: event.clientY };
}

function runContextAction(action: ContextAction) {
  if (!context.value) return;
  emit('context-action', { action, id: context.value.id });
  context.value = null;
}

function closeContext() {
  context.value = null;
}

onMounted(() => window.addEventListener('click', closeContext));
onUnmounted(() => window.removeEventListener('click', closeContext));
</script>

<template>
  <div class="db-workspace-tabs" @contextmenu.prevent>
    <div class="db-workspace-tabs-scroll" role="tablist" aria-label="数据库工作区标签">
      <button
        v-for="item in items"
        :key="item.id"
        class="db-workspace-tab"
        :class="{ active: modelValue === item.id, sticky: item.sticky }"
        type="button"
        role="tab"
        :aria-selected="modelValue === item.id"
        :aria-label="`${item.label}工作区`"
        :draggable="!item.sticky"
        @click="selectTab(item.id)"
        @dragstart="startDrag($event, item.id)"
        @dragover.prevent
        @drop="dropTab($event, item.id)"
        @contextmenu.stop.prevent="openContext($event, item)"
      >
        <ListIcon v-if="item.kind === 'list'" :size="14" aria-hidden="true" />
        <DatabaseZap v-else-if="item.dbType === 'redis'" :size="14" aria-hidden="true" />
        <Database v-else :size="14" aria-hidden="true" />
        <span>{{ item.label }}</span>
        <span
          v-if="!item.sticky"
          class="db-workspace-tab-close"
          role="button"
          tabindex="0"
          aria-label="关闭标签"
          @click.stop="emit('close', item.id)"
          @keydown.enter.stop="emit('close', item.id)"
          @keydown.space.prevent.stop="emit('close', item.id)"
        >
          <X :size="13" aria-hidden="true" />
        </span>
      </button>
    </div>
    <div
      v-if="context"
      class="db-workspace-tab-menu"
      :style="{ left: `${context.x}px`, top: `${context.y}px` }"
      role="menu"
      @click.stop
    >
      <button type="button" role="menuitem" @click="runContextAction('close')">关闭</button>
      <button type="button" role="menuitem" @click="runContextAction('close-others')">关闭其他</button>
      <button type="button" role="menuitem" @click="runContextAction('close-all')">关闭全部</button>
      <button type="button" role="menuitem" @click="runContextAction('copy')">复制名称</button>
    </div>
  </div>
</template>

<style scoped>
.db-workspace-tabs{position:relative;min-width:0;height:31px;border:1px solid var(--el-border-color,#dcdfe6);border-bottom:0;background:var(--el-bg-color,#fff);overflow:hidden}
.db-workspace-tabs-scroll{display:flex;align-items:stretch;height:100%;overflow-x:auto;overflow-y:hidden;scrollbar-width:thin}
.db-workspace-tab{display:flex;align-items:center;gap:5px;flex:none;min-width:88px;height:30px;padding:0 8px;border:0;border-right:1px solid var(--el-border-color,#dcdfe6);border-bottom:2px solid transparent;background:var(--el-bg-color,#fff);color:var(--el-text-color-secondary,#606266);font-size:12px;cursor:pointer;user-select:none}
.db-workspace-tab:hover{background:var(--el-fill-color-light,#f5f7fa);color:var(--el-text-color-primary,#303133)}
.db-workspace-tab.active{border-bottom-color:var(--el-color-primary,#409eff);background:var(--el-color-primary-light-9,#ecf5ff);color:var(--el-color-primary,#409eff)}
.db-workspace-tab.sticky{position:sticky;left:0;z-index:1;min-width:72px;box-shadow:2px 0 8px rgba(0,0,0,.08)}
.db-workspace-tab span:not(.db-workspace-tab-close){min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.db-workspace-tab-close{display:grid;place-items:center;flex:none;width:18px;height:18px;border-radius:3px;color:inherit}
.db-workspace-tab-close:hover,.db-workspace-tab-close:focus-visible{background:var(--el-fill-color,#e5e7eb);outline:none}
.db-workspace-tab-menu{position:fixed;z-index:3200;min-width:132px;padding:4px;border:1px solid var(--el-border-color,#dcdfe6);border-radius:5px;background:var(--el-bg-color,#fff);box-shadow:0 8px 24px rgba(20,30,35,.18)}
.db-workspace-tab-menu button{display:block;width:100%;padding:7px 10px;border:0;border-radius:3px;background:none;color:inherit;text-align:left;font-size:12px;cursor:pointer}
.db-workspace-tab-menu button:hover{background:var(--el-fill-color-light,#f5f7fa)}
@media(max-width:720px){.db-workspace-tabs{height:30px}.db-workspace-tab{height:29px;min-width:78px}.db-workspace-tab.sticky{min-width:62px}}
</style>
