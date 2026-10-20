import { describe, expect, it } from 'vitest';
import { buildDiagram, fieldHandle, layoutDiagram, tableHeight, TABLE_WIDTH } from '../utils/databaseDiagram';
import type { MysqlDiagram } from '../api/databaseManagement';

const column = (table: string, name: string) => ({ table_name: table, name, type: 'int', column_key: 'PRI', comment: '' });
const relation = (source: string, target: string, name = 'fk') => ({ name, source, target, source_column: 'id', target_column: 'id' });
function assertNoOverlap(data: MysqlDiagram) {
  const { nodes } = buildDiagram(data);
  for (let i = 0; i < nodes.length; i++) {
    expect(Number.isFinite(nodes[i].position.x)).toBe(true);
    expect(Number.isFinite(nodes[i].position.y)).toBe(true);
    for (let j = i + 1; j < nodes.length; j++) {
      const a = nodes[i], b = nodes[j];
      const separated = a.position.x + TABLE_WIDTH <= b.position.x || b.position.x + TABLE_WIDTH <= a.position.x || a.position.y + tableHeight(a.data!) <= b.position.y || b.position.y + tableHeight(b.data!) <= a.position.y;
      expect(separated, `${a.id} overlaps ${b.id}`).toBe(true);
    }
  }
  return nodes;
}
describe('ER workflow graph', () => {
  it('connects exact foreign key fields, including multiple columns of one constraint', () => {
    const graph = buildDiagram({ columns: [column('orders', 'id'), column('orders', 'tenant'), column('users', 'id'), column('users', 'tenant')], relations: [relation('orders', 'users'), { ...relation('orders', 'users'), source_column: 'tenant', target_column: 'tenant' }] });
    expect(graph.edges).toHaveLength(2);
    expect(graph.edges[0]).toMatchObject({ source: 'orders', target: 'users', sourceHandle: fieldHandle('id'), targetHandle: fieldHandle('id'), updatable: false });
    expect(graph.edges[1].sourceHandle).toBe(fieldHandle('tenant'));
    expect(new Set(graph.edges.map(edge => edge.id)).size).toBe(2);
    expect(graph.nodes[0].data!.foreignKeys).toEqual(['id', 'tenant']);
  });
  it('handles cycles, self references and disconnected tall tables without overlap', () => {
    const data = { columns: ['a', 'b', 'c'].map(name => column(name, 'id')).concat(Array.from({ length: 45 }, (_, i) => column('tall', `c${i}`))), relations: [relation('a', 'b'), relation('b', 'a'), relation('a', 'a')] };
    const nodes = assertNoOverlap(data);
    expect(nodes).toHaveLength(4);
  });
  it('packs tables with no foreign keys into readable rows using actual field heights', () => {
    const data = { columns: Array.from({ length: 17 }, (_, t) => Array.from({ length: t + 1 }, (_, i) => column(`table${t}`, `c${i}`))).flat(), relations: [] };
    expect(assertNoOverlap(data)).toHaveLength(17);
  });
  it('skips missing endpoints and never creates fictional relationships', () => {
    const graph = buildDiagram({ columns: [column('a', 'id'), column('b', 'id')], relations: [relation('a', 'missing'), { ...relation('a', 'b'), source_column: 'missing' }] });
    expect(graph.edges).toEqual([]);
    expect(buildDiagram({ columns: [], relations: [] })).toEqual({ nodes: [], edges: [] });
  });
  it('rearranges positions without changing metadata or mutating the original nodes', () => {
    const graph = buildDiagram({ columns: [column('a', 'id'), column('b', 'id')], relations: [relation('a', 'b')] });
    graph.nodes[0].position = { x: -500, y: 700 };
    const result = layoutDiagram(graph.nodes, graph.edges);
    expect(graph.nodes[0].position).toEqual({ x: -500, y: 700 });
    expect(result[0].position).not.toEqual(graph.nodes[0].position);
    expect(result[0].data).toBe(graph.nodes[0].data);
  });
});
