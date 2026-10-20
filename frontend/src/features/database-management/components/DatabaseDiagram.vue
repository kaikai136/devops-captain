<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, useId } from 'vue';
import { VueFlow, useVueFlow, type Node, type Edge } from '@vue-flow/core';
import { Background } from '@vue-flow/background';
import { Controls } from '@vue-flow/controls';
import { MiniMap } from '@vue-flow/minimap';
import { Maximize, RefreshCw, LayoutGrid, X } from '@lucide/vue';
import '@vue-flow/core/dist/style.css';
import '@vue-flow/core/dist/theme-default.css';
import '@vue-flow/controls/dist/style.css';
import '@vue-flow/minimap/dist/style.css';
import DatabaseDiagramTable from './DatabaseDiagramTable.vue';
import { buildDiagram, layoutDiagram, tableHeight, TABLE_WIDTH, type DiagramTableData } from '../utils/databaseDiagram';
import { getMysqlDiagram, type MysqlDiagram } from '../api/databaseManagement';
import { errorMessage } from '@shared/utils/errors';

const props = defineProps<{ assetId: number; database: string }>();
const flowId = `database-er-${useId()}`;
const { fitView, setCenter, viewport, onNodesInitialized } = useVueFlow({ id: flowId });
const nodes = shallowRef<Node<DiagramTableData>[]>([]);
const edges = shallowRef<Edge[]>([]);
const loading = ref(false);
const error = ref('');
const selectedTable = ref('');
const selectedRelation = ref<MysqlDiagram['relations'][number] | null>(null);
const zoomPercent = computed(() => Math.round(viewport.value.zoom * 100));
const canvas = ref<HTMLElement | null>(null);
let version = 0;
let disposed = false;
let needsFit = true;
let observer: ResizeObserver | null = null;

async function fitDiagram() {
  await nextTick();
  if (disposed || !canvas.value?.clientWidth || !canvas.value?.clientHeight || !nodes.value.length) return;
  needsFit = !(await fitView({ padding: 0.18, minZoom: 0.08, maxZoom: 1, duration: 250 }));
}
function arrange() {
  nodes.value = layoutDiagram(nodes.value, edges.value);
  needsFit = true;
  void fitDiagram();
}
function focusTable(name: string) {
  const node = nodes.value.find(item => item.id === name);
  selectedTable.value = name;
  selectedRelation.value = null;
  nodes.value = nodes.value.map(item => ({ ...item, selected: item.id === name }));
  if (node) void setCenter(node.position.x + TABLE_WIDTH / 2, node.position.y + tableHeight(node.data!) / 2, { zoom: 1, duration: 300 });
}
async function load() {
  const request = ++version;
  loading.value = true; error.value = '';
  try {
    const result = await getMysqlDiagram(props.assetId, props.database);
    if (request !== version) return;
    const diagram = buildDiagram(result);
    nodes.value = diagram.nodes; edges.value = diagram.edges;
    selectedTable.value = ''; selectedRelation.value = null;
    needsFit = true;
    void fitDiagram();
  } catch (err) { if (request === version) error.value = errorMessage(err); }
  finally { if (request === version) loading.value = false; }
}
onNodesInitialized(() => { if (needsFit) void fitDiagram(); });
onMounted(load);
onMounted(() => {
  observer = new ResizeObserver(() => { if (needsFit) void fitDiagram(); });
  if (canvas.value) observer.observe(canvas.value);
});
onUnmounted(() => { disposed = true; version++; observer?.disconnect(); });
</script>

<template>
  <section class="diagram-panel" v-loading="loading">
    <header class="diagram-toolbar">
      <div class="diagram-heading"><strong>{{ database }} · ER 图</strong><span>{{ nodes.length }} 张表 · {{ edges.length }} 条字段关系</span><el-tag size="small" type="info">只读</el-tag></div>
      <div class="diagram-actions">
        <el-select :model-value="selectedTable" filterable clearable placeholder="搜索并定位表" aria-label="搜索并定位表" @change="focusTable"><el-option v-for="node in nodes" :key="node.id" :value="node.id" :label="node.id" /></el-select>
        <el-button :disabled="!nodes.length || loading" @click="arrange"><LayoutGrid :size="14" />自动布局</el-button>
        <el-button :disabled="!nodes.length" @click="fitDiagram"><Maximize :size="14" />适应窗口</el-button>
        <el-button :disabled="loading" @click="load"><RefreshCw :size="14" />刷新</el-button>
      </div>
    </header>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <div ref="canvas" class="diagram-canvas">
      <VueFlow :id="flowId" v-model:nodes="nodes" v-model:edges="edges" :nodes-connectable="false" :edges-updatable="false" :delete-key-code="null" :min-zoom="0.08" :max-zoom="2" :zoom-on-double-click="false" :auto-pan-on-node-drag="true" aria-label="数据库 ER 关系画布" @edge-click="selectedRelation = $event.edge.data" @pane-click="selectedRelation = null" @node-click="selectedTable = $event.node.id; selectedRelation = null">
        <template #node-table="node"><DatabaseDiagramTable :data="node.data" :selected="node.selected" /></template>
        <Background :gap="22" :size="1" pattern-color="var(--el-border-color)" />
        <Controls position="bottom-left" :show-interactive="false" />
        <MiniMap position="bottom-right" pannable zoomable :width="180" :height="120" node-color="var(--el-color-primary-light-5)" node-stroke-color="var(--el-color-primary)" mask-color="var(--er-minimap-mask)" aria-label="ER 图导航小地图" />
      </VueFlow>
      <div class="diagram-hint"><span>{{ zoomPercent }}%</span>拖动空白处平移 · 滚轮缩放 · 拖动表头布局<template v-if="nodes.length && !edges.length"> · 当前库未定义外键</template></div>
      <aside v-if="selectedRelation" class="diagram-relation" aria-label="外键关系详情"><header><strong>{{ selectedRelation.name }}</strong><el-button text circle aria-label="关闭关系详情" @click="selectedRelation = null"><X :size="14" /></el-button></header><p>{{ selectedRelation.source }}.{{ selectedRelation.source_column }}</p><span>引用 ↓</span><p>{{ selectedRelation.target }}.{{ selectedRelation.target_column }}</p></aside>
      <el-empty v-if="!loading && !error && !nodes.length" class="diagram-empty" description="当前数据库没有表" />
    </div>
  </section>
</template>

<style scoped>
.diagram-panel{height:100%;display:flex;flex-direction:column;min-width:0;min-height:0;background:var(--el-bg-color);--er-minimap-mask:color-mix(in srgb,var(--el-fill-color) 75%,transparent)}.diagram-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 14px;border-bottom:1px solid var(--el-border-color)}.diagram-heading,.diagram-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.diagram-heading strong{font-size:14px}.diagram-heading>span{color:var(--el-text-color-secondary);font-size:12px}.diagram-actions .el-select{width:200px}.diagram-actions .el-button+.el-button{margin-left:0}.diagram-actions :deep(.el-select__wrapper){box-shadow:0 0 0 1px var(--el-border-color) inset!important}.diagram-actions :deep(.el-select__wrapper.is-focused){box-shadow:0 0 0 1px var(--el-color-primary) inset!important}.diagram-canvas{position:relative;flex:1;min-height:0;overflow:hidden;background:var(--el-fill-color-lighter)}.diagram-hint{position:absolute;top:14px;left:14px;right:14px;width:fit-content;max-width:calc(100% - 28px);padding:7px 10px;border:1px solid var(--el-border-color-lighter);border-radius:5px;background:var(--el-bg-color);color:var(--el-text-color-secondary);font-size:11px;pointer-events:none}.diagram-hint span{font-variant-numeric:tabular-nums;color:var(--el-text-color-primary);margin-right:10px}.diagram-relation{position:absolute;top:56px;right:14px;width:min(300px,calc(100% - 48px));padding:12px;background:var(--el-bg-color);border:1px solid var(--el-border-color);border-radius:8px;box-shadow:0 3px 16px #00000014;font-size:12px}.diagram-relation header{display:flex;justify-content:space-between;align-items:center;gap:8px}.diagram-relation strong,.diagram-relation p{overflow-wrap:anywhere}.diagram-relation span{color:var(--el-text-color-secondary)}.diagram-empty{position:absolute;inset:0;pointer-events:none;display:flex;justify-content:center}.diagram-canvas :deep(.vue-flow__controls){overflow:hidden;border:1px solid var(--el-border-color);border-radius:5px;box-shadow:0 2px 8px #00000014}.diagram-canvas :deep(.vue-flow__controls-button){background:var(--el-bg-color);color:var(--el-text-color-primary);border-color:var(--el-border-color);fill:currentColor}.diagram-canvas :deep(.vue-flow__controls-button:hover){background:var(--el-fill-color)}.diagram-canvas :deep(.vue-flow__minimap){background:var(--el-bg-color);border:1px solid var(--el-border-color);border-radius:6px;overflow:hidden}.diagram-canvas :deep(.vue-flow__edge-text){fill:var(--el-text-color-primary);font-size:10px}.diagram-canvas :deep(.vue-flow__edge-textbg){fill:var(--el-bg-color)}.diagram-canvas :deep(.vue-flow__edge.selected .vue-flow__edge-path){stroke-width:3}.diagram-canvas :deep(.vue-flow__node:focus-visible){outline:2px solid var(--el-color-primary);outline-offset:4px}@media(max-width:760px){.diagram-toolbar{padding:10px}.diagram-actions{gap:6px}.diagram-actions .el-select{width:170px}.diagram-hint{font-size:10px}.diagram-canvas :deep(.vue-flow__minimap){display:none}}
</style>
