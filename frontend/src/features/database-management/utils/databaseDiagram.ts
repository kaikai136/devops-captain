import { graphlib, layout } from '@dagrejs/dagre';
import { MarkerType, type Edge, type Node } from '@vue-flow/core';
import type { MysqlDiagram } from '../api/databaseManagement';

export interface DiagramTableData {
  name: string;
  fields: MysqlDiagram['columns'];
  foreignKeys: string[];
  referencedKeys: string[];
}
export const TABLE_WIDTH = 300;
export const tableHeight = (data: DiagramTableData) => 44 + data.fields.length * 28 + 2;
export const fieldHandle = (name: string) => `field-${encodeURIComponent(name)}`;

export function buildDiagram(data: MysqlDiagram): { nodes: Node<DiagramTableData>[]; edges: Edge[] } {
  const tables = new Map<string, DiagramTableData>();
  for (const column of data.columns) {
    if (!tables.has(column.table_name)) tables.set(column.table_name, { name: column.table_name, fields: [], foreignKeys: [], referencedKeys: [] });
    tables.get(column.table_name)!.fields.push(column);
  }
  const edges: Edge[] = [];
  for (const [index, relation] of data.relations.entries()) {
    const source = tables.get(relation.source), target = tables.get(relation.target);
    // Do not invent table/column endpoints when metadata is incomplete.
    if (!source?.fields.some(field => field.name === relation.source_column) || !target?.fields.some(field => field.name === relation.target_column)) continue;
    source.foreignKeys.push(relation.source_column);
    target.referencedKeys.push(relation.target_column);
    edges.push({
      id: `relation-${index}`, source: relation.source, target: relation.target,
      sourceHandle: fieldHandle(relation.source_column), targetHandle: fieldHandle(relation.target_column),
      type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--el-color-primary)' },
      label: relation.name, data: relation, updatable: false,
      style: { stroke: 'var(--el-color-primary)', strokeWidth: 1.6 },
    });
  }
  const nodes: Node<DiagramTableData>[] = [...tables.values()].map(table => ({
    id: table.name, type: 'table', position: { x: 0, y: 0 }, data: table,
    dragHandle: '.er-node-header', connectable: false,
  }));
  return { nodes: layoutDiagram(nodes, edges), edges };
}

export function layoutDiagram(nodes: Node<DiagramTableData>[], edges: Edge[]): Node<DiagramTableData>[] {
  const related = new Set(edges.flatMap(edge => [edge.source, edge.target]));
  const graph = new graphlib.Graph({ multigraph: true });
  graph.setGraph({ rankdir: 'LR', nodesep: 64, ranksep: 160, marginx: 40, marginy: 40 });
  graph.setDefaultEdgeLabel(() => ({}));
  nodes.filter(node => related.has(node.id)).forEach(node => graph.setNode(node.id, { width: TABLE_WIDTH, height: tableHeight(node.data!) }));
  edges.forEach(edge => graph.setEdge(edge.source, edge.target, {}, edge.id));
  if (related.size) layout(graph);
  const positions = new Map<string, { x: number; y: number }>();
  let bottom = 0;
  for (const node of nodes.filter(item => related.has(item.id))) {
    const result = graph.node(node.id);
    positions.set(node.id, { x: result.x - TABLE_WIDTH / 2, y: result.y - tableHeight(node.data!) / 2 });
    bottom = Math.max(bottom, result.y + tableHeight(node.data!) / 2);
  }
  const isolated = nodes.filter(node => !related.has(node.id));
  const columns = Math.min(4, Math.max(1, Math.ceil(Math.sqrt(isolated.length))));
  let y = related.size ? bottom + 100 : 40;
  for (let i = 0; i < isolated.length; i += columns) {
    const row = isolated.slice(i, i + columns);
    row.forEach((node, column) => positions.set(node.id, { x: 40 + column * (TABLE_WIDTH + 64), y }));
    y += Math.max(...row.map(node => tableHeight(node.data!))) + 64;
  }
  return nodes.map(node => ({ ...node, position: positions.get(node.id)! }));
}
