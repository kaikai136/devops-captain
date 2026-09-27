import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function readPanel() {
  return readFileSync(fileURLToPath(new URL('../components/DatabaseManagementPanel.vue', import.meta.url)), 'utf8');
}

describe('database management HexHub asset tree', () => {
  it('keeps the database tree inside the expanded asset node', () => {
    const panel = readPanel();

    expect(panel).toContain('db-asset-children');
    expect(panel).toContain('expandedAssets.includes(entry.asset!.id)');
    expect(panel).toContain('toggleAsset(entry.asset!)');
    expect(panel).not.toContain('db-selected-tree');
    expect(panel).not.toContain('class="db-tree-node" :class="{ active: activeTable === item.name }"');
    expect(panel).toContain('toggleCategory(category.key as');
    expect(panel).toContain('class="db-tree-object-row"');
    expect(panel).toContain('db-object-items');
    expect(panel).toContain('v-if="expandedCategory === category.key"');
    expect(panel).toContain('@click="selectTable(object.name)"');
    expect(panel).toContain('v-if="expandedQuery"');
    expect(panel).toContain('justify-content:flex-start !important');
    expect(panel).toContain('text-align:left !important');
    expect(panel).toContain("schemas.length ? schemas : ['']");
    expect(panel).toContain("!schemas.length && expandedDatabase === name");
  });

  it('provides compact toolbar, search toggle, and per-asset actions', () => {
    const panel = readPanel();

    expect(panel).toContain('searchExpanded');
    expect(panel).toContain('toggleSearch');
    expect(panel).toContain('db-sidebar-search');
    expect(panel).toContain('db-asset-more');
    expect(panel).toContain('MoreHorizontal');
  });

  it('adds a HexHub-style workspace tab strip without changing the asset tree', () => {
    const panel = readPanel();

    expect(panel).toContain('DatabaseWorkspaceTabs');
    expect(panel).toContain("[{ id: 'list', kind: 'list', label: '列表', sticky: true }]");
    expect(panel).toContain('activeWorkspaceTabId');
    expect(panel).toContain('workspaceSnapshots');
    expect(panel).toContain('handleWorkspaceContextAction');
    expect(panel).toContain('openAssetWorkspace(asset)');
    expect(panel).toContain("activeWorkspaceTabId === 'list'");
    expect(panel).toContain('表列表');
    expect(panel.indexOf('<main class="db-main">')).toBeLessThan(panel.indexOf('<DatabaseWorkspaceTabs'));
    expect(panel).toContain('.db-main>.db-workspace-tabs{flex:none');
  });

  it('maps Redis and relational assets to distinct local icon styles', () => {
    const panel = readPanel();

    expect(panel).toContain('isRedisType(entry.asset!.dbType)');
    expect(panel).toContain('db-asset-icon redis');
    expect(panel).toContain('v-for="db in 16"');
    expect(panel).toContain('{{ redisDbCounts[db - 1] }}');
    expect(panel).toContain('selectRedisDatabase(db - 1)');
    expect(panel).not.toContain('键空间');
    expect(panel).toContain('.db-asset-icon.redis');
    expect(panel).toContain('.db-workspace{grid-template-columns:284px');
  });

  it('shows category totals for the selected database and schema', () => {
    const panel = readPanel();

    expect(panel).toContain("const objectCategories: ObjectCategory[] = ['table', 'view', 'procedure', 'function']");
    expect(panel).toContain('listDatabaseObjects(assetId, database, owner || undefined, category)');
    expect(panel).toContain("objectCounts[category.key as ObjectCategory] ?? '-'");
    expect(panel).toContain('objectCountVersion++');
    expect(panel).toContain('class="db-tree-count">0</small>');
  });

  it('keeps the workspace fitted to the available content height', () => {
    const panel = readPanel();

    expect(panel).toContain('.db-workspace{height:100%;min-height:0');
    expect(panel).toContain('.db-shell>.db-workspace{width:100%;height:auto;flex:1 1 auto;align-self:stretch;min-height:0}');
    expect(panel).not.toContain('min-height:600px');
  });
});
