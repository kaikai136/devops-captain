<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import type { InputInstance } from 'element-plus';
import AppIcon from '@shared/components/AppIcon.vue';
import type { TerminalFileEntry } from '../../types';
import type { SftpRenameState } from '../../composables/useSftpBrowser';
import { calculateVirtualWindow } from '../../utils/virtualList';

const props = defineProps<{
  active: boolean;
  path: string;
  entries: TerminalFileEntry[];
  selectedPaths: Set<string>;
  loading: boolean;
  error: string;
  dragOver: boolean;
  marqueeActive: boolean;
  marqueeStyle: Record<string, string>;
  rename: SftpRenameState | null;
  formatSize: (entry: TerminalFileEntry) => string;
  text: (value?: string | number) => string;
  isParent: (entry: TerminalFileEntry) => boolean;
}>();
const emit = defineEmits<{
  select: [entry: TerminalFileEntry, event: MouseEvent | KeyboardEvent];
  entryContext: [entry: TerminalFileEntry, event: MouseEvent];
  directoryContext: [event: MouseEvent];
  marqueeStart: [event: MouseEvent];
  dragStart: [entry: TerminalFileEntry, event: DragEvent];
  open: [entry: TerminalFileEntry];
  dragEnter: [event: DragEvent];
  dragOver: [event: DragEvent];
  dragLeave: [event: DragEvent];
  drop: [event: DragEvent];
  renameName: [name: string];
  saveRename: [];
  cancelRename: [];
}>();

const list = ref<HTMLElement | null>(null);
const renameInput = ref<InputInstance | null>(null);
const scrollTop = ref(0);
const viewportHeight = ref(0);
let resizeObserver: ResizeObserver | null = null;

const viewportWindow = computed(() => calculateVirtualWindow(
  props.entries.length,
  scrollTop.value,
  viewportHeight.value,
));
const visibleEntries = computed(() => props.entries.slice(viewportWindow.value.start, viewportWindow.value.end));
const virtualSpacerStyle = computed(() => ({ height: `${viewportWindow.value.totalHeight}px` }));
const virtualWindowStyle = computed(() => ({ transform: `translateY(${viewportWindow.value.offset}px)` }));

watch(() => props.rename?.path, async (path) => {
  if (!path) return;
  await nextTick();
  renameInput.value?.focus();
  renameInput.value?.input?.select();
});
watch(() => props.path, () => {
  scrollTop.value = 0;
  if (list.value) list.value.scrollTop = 0;
});
watch(() => props.entries.length, async () => {
  await nextTick();
  clampScrollPosition();
});

onMounted(() => {
  syncViewportHeight();
  if (typeof ResizeObserver === 'undefined' || !list.value) return;
  resizeObserver = new ResizeObserver(syncViewportHeight);
  resizeObserver.observe(list.value);
});
onBeforeUnmount(() => resizeObserver?.disconnect());

function syncViewportHeight() {
  viewportHeight.value = list.value?.clientHeight ?? 0;
}
function clampScrollPosition() {
  const element = list.value;
  if (!element) return;
  const maxScrollTop = Math.max(0, viewportWindow.value.totalHeight - element.clientHeight);
  if (element.scrollTop > maxScrollTop) element.scrollTop = maxScrollTop;
  scrollTop.value = element.scrollTop;
}
function handleScroll(event: Event) {
  scrollTop.value = (event.currentTarget as HTMLElement).scrollTop;
}
function openDirectory(entry: TerminalFileEntry) {
  if (!props.rename || props.rename.path !== entry.path) {
    if (entry.type === 'directory') emit('open', entry);
  }
}

defineExpose({ list });
</script>

<template>
  <div class="terminal-file-path">
    <span>{{ path }}</span>
    <el-button circle title="收藏路径" aria-label="收藏路径"><AppIcon name="folder" :size="14" /></el-button>
  </div>
  <div class="terminal-file-table">
    <div class="terminal-file-table-head">
      <el-button text>名称 <em>▲</em></el-button><span>修改时间</span><span>大小</span><span>权限</span><span>所有者</span><span>组</span>
    </div>
    <div
      ref="list"
      class="terminal-file-list"
      :class="{ 'drag-over': dragOver, selecting: marqueeActive }"
      @scroll="handleScroll"
      @contextmenu="emit('directoryContext', $event)"
      @mousedown="emit('marqueeStart', $event)"
      @dragenter="emit('dragEnter', $event)"
      @dragover="emit('dragOver', $event)"
      @dragleave="emit('dragLeave', $event)"
      @drop="emit('drop', $event)"
    >
      <div class="terminal-file-virtual-spacer" :style="virtualSpacerStyle">
        <div class="terminal-file-virtual-window" :style="virtualWindowStyle">
          <div
            v-for="entry in visibleEntries"
            :key="entry.path"
            class="terminal-file-item"
            :class="{ selected: selectedPaths.has(entry.path), parent: isParent(entry) }"
            :data-terminal-file-path="entry.path"
            :draggable="active && entry.type === 'file' && selectedPaths.has(entry.path)"
            role="button"
            :tabindex="active ? 0 : -1"
            :aria-disabled="!active"
            @click="emit('select', entry, $event)"
            @contextmenu="emit('entryContext', entry, $event)"
            @mousedown="!selectedPaths.has(entry.path) && emit('marqueeStart', $event)"
            @dragstart="emit('dragStart', entry, $event)"
            @dblclick="openDirectory(entry)"
            @keydown.enter.prevent="openDirectory(entry)"
          >
            <span class="terminal-file-name">
              <AppIcon :name="entry.type === 'directory' ? 'folder' : 'settings'" :size="15" />
              <el-input
                v-if="rename?.path === entry.path"
                ref="renameInput"
                :model-value="rename.draftName"
                class="terminal-file-rename-input"
                :disabled="rename.saving"
                @input="emit('renameName', $event)"
                @click.stop
                @dblclick.stop
                @keydown.enter.prevent.stop="emit('saveRename')"
                @keydown.esc.prevent.stop="emit('cancelRename')"
                @blur="emit('saveRename')"
              />
              <strong v-else>{{ entry.name }}</strong>
            </span>
            <time>{{ entry.modifiedAt }}</time>
            <span class="terminal-file-size">{{ formatSize(entry) }}</span>
            <span class="terminal-file-permissions">{{ text(entry.permissions) }}</span>
            <span>{{ text(entry.owner) }}</span><span>{{ text(entry.group) }}</span>
          </div>
        </div>
      </div>
      <p v-if="!active" class="terminal-tree-empty">请选择服务器</p>
      <p v-else-if="loading" class="terminal-tree-empty">目录加载中...</p>
      <p v-else-if="error" class="terminal-tree-empty">{{ error }}</p>
      <div v-if="dragOver" class="terminal-file-drop-hint"><AppIcon name="upload" :size="22" /><strong>释放后上传到当前目录</strong></div>
      <div v-if="marqueeActive" class="terminal-file-marquee" :style="marqueeStyle"></div>
    </div>
  </div>
</template>
