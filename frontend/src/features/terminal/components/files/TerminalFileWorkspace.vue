<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { Compartment, EditorState } from '@codemirror/state';
import { EditorView, drawSelection, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from '@codemirror/view';
import { bracketMatching, defaultHighlightStyle, foldGutter, foldKeymap, indentOnInput, syntaxHighlighting } from '@codemirror/language';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { closeBrackets, closeBracketsKeymap } from '@codemirror/autocomplete';
import { highlightSelectionMatches, openSearchPanel, search, searchKeymap } from '@codemirror/search';
import AppIcon from '@shared/components/AppIcon.vue';
import { buildTerminalFileDownloadRawUrl } from '../../api/terminal';
import type { TerminalFileTab } from '../../composables/useTerminalFiles';
import { terminalFileLanguageExtension } from '../../utils/fileEditor';

const props = defineProps<{ tab: TerminalFileTab; active: boolean }>();
const emit = defineEmits<{ change: [content: string]; save: []; reload: []; edit: [] }>();
const editorHost = ref<HTMLElement | null>(null);
const wrapLines = ref(false);
const readOnly = computed(() => props.tab.mode === 'preview');
const readOnlyCompartment = new Compartment();
const wrapCompartment = new Compartment();
let view: EditorView | null = null;
function destroyEditor() { view?.destroy(); view = null; }
function createEditor() {
  destroyEditor();
  if (!editorHost.value || props.tab.loading || props.tab.error || props.tab.kind !== 'text') return;
  view = new EditorView({
    parent: editorHost.value,
    state: EditorState.create({
      doc: props.tab.content,
      extensions: [
        lineNumbers(), foldGutter(), drawSelection(), history(), highlightActiveLine(), highlightActiveLineGutter(), indentOnInput(),
        bracketMatching(), closeBrackets(), search({ top: true }), highlightSelectionMatches(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }), terminalFileLanguageExtension(props.tab.name),
        EditorState.tabSize.of(2),
        readOnlyCompartment.of([EditorState.readOnly.of(readOnly.value), EditorView.editable.of(!readOnly.value)]),
        wrapCompartment.of(wrapLines.value ? EditorView.lineWrapping : []),
        keymap.of([
          { key: 'Mod-s', run: () => { if (!readOnly.value) emit('save'); return true; } },
          indentWithTab, ...defaultKeymap, ...historyKeymap, ...foldKeymap, ...closeBracketsKeymap, ...searchKeymap,
        ]),
        EditorView.updateListener.of(update => { if (update.docChanged) emit('change', update.state.doc.toString()); }),
        EditorView.theme({
          '&': { height: '100%', fontSize: '13px', backgroundColor: 'var(--el-bg-color, #fff)', color: 'var(--el-text-color-primary, #243447)' },
          '.cm-scroller': { overflow: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' },
          '.cm-gutters': { backgroundColor: 'var(--el-fill-color-light, #f4f7fb)', color: 'var(--el-text-color-secondary, #71839a)', border: 'none' },
          '.cm-content': { minHeight: '100%' },
        }),
      ],
    }),
  });
  if (props.active && !readOnly.value) view.focus();
}
watch(() => [editorHost.value, props.tab.revision, props.tab.loading] as const, createEditor, { flush: 'post' });
watch(readOnly, value => view?.dispatch({ effects: readOnlyCompartment.reconfigure([EditorState.readOnly.of(value), EditorView.editable.of(!value)]) }));
watch(wrapLines, value => view?.dispatch({ effects: wrapCompartment.reconfigure(value ? EditorView.lineWrapping : []) }));
watch(() => props.active, value => { if (value) { view?.requestMeasure(); if (!readOnly.value) view?.focus(); } }, { flush: 'post' });
onBeforeUnmount(destroyEditor);
function showSearch() { if (view) openSearchPanel(view); }
function download() {
  const anchor = document.createElement('a');
  anchor.href = buildTerminalFileDownloadRawUrl(props.tab.hostId, props.tab.path, 'auto');
  anchor.download = props.tab.name;
  anchor.click();
}
</script>

<template>
  <section v-show="active" class="terminal-file-workspace" @keydown.stop @contextmenu.stop>
    <header class="terminal-file-workspace-toolbar">
      <div class="terminal-file-workspace-location"><strong>{{ tab.name }}</strong><span :title="`${tab.nodeName} · ${tab.path}`">{{ tab.nodeName }} · {{ tab.path }}</span></div>
      <div class="terminal-file-workspace-actions">
        <el-button :disabled="tab.loading || tab.saving" title="重新加载" @click="emit('reload')"><AppIcon name="refresh" :size="15" /></el-button>
        <template v-if="tab.kind === 'text' && !tab.loading && !tab.error">
          <el-button title="搜索 / 替换" @click="showSearch"><AppIcon name="search" :size="15" /></el-button>
          <el-button :aria-pressed="wrapLines" @click="wrapLines = !wrapLines">{{ wrapLines ? '取消换行' : '自动换行' }}</el-button>
          <el-button v-if="readOnly" @click="emit('edit')">使用内置编辑器打开</el-button>
          <el-button v-else type="primary" :loading="tab.saving" :disabled="!tab.dirty || tab.saving" title="保存 (Ctrl/Cmd+S)" @click="emit('save')">保存</el-button>
        </template>
        <el-button title="下载文件" aria-label="下载文件" @click="download"><AppIcon name="download" :size="15" /></el-button>
      </div>
    </header>
    <el-alert v-if="tab.saveError" type="error" :title="tab.saveError" :closable="false" />
    <div v-if="tab.loading" class="terminal-file-workspace-message">正在读取远程文件…</div>
    <div v-else-if="tab.error" class="terminal-file-workspace-message error">{{ tab.error }}<el-button @click="emit('reload')">重试</el-button></div>
    <div v-else-if="tab.kind === 'image'" class="terminal-file-image-preview"><img :src="tab.imageUrl" :alt="tab.name"></div>
    <div v-else-if="tab.kind === 'binary'" class="terminal-file-workspace-message"><strong>{{ tab.name }}</strong><span>文件类型：{{ tab.contentType || '未知' }}</span><span>此文件不是 UTF-8 文本或支持的图片，无法在线预览或编辑。</span><el-button type="primary" @click="download">下载文件</el-button></div>
    <div v-else ref="editorHost" class="terminal-file-code-editor"></div>
    <footer class="terminal-file-workspace-status"><span>{{ tab.kind !== 'text' || readOnly ? '只读预览' : tab.saving ? '保存中…' : tab.dirty ? '有未保存的修改' : '已保存' }}</span><span>{{ tab.byteSize.toLocaleString() }} 字节</span><span v-if="tab.kind === 'text'">UTF-8 · {{ tab.lineEnding === '\r\n' ? 'CRLF' : tab.lineEnding === '\r' ? 'CR' : 'LF' }}</span></footer>
  </section>
</template>
