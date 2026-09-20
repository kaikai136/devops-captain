import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const template = readFileSync(fileURLToPath(new URL('../../UserManager.vue', import.meta.url)), 'utf8');
const tableTemplate = readFileSync(fileURLToPath(new URL('../UserTable.vue', import.meta.url)), 'utf8');
const paginationTemplate = readFileSync(fileURLToPath(new URL('../../../../shared/components/AppPagination.vue', import.meta.url)), 'utf8');
const styles = readFileSync(fileURLToPath(new URL('../../../../styles/tools/user-manager.css', import.meta.url)), 'utf8');
const tableStyles = readFileSync(fileURLToPath(new URL('../../../../styles/base/data-table.css', import.meta.url)), 'utf8');

describe('UserManager layout', () => {
  it('keeps search and list content in separate responsive sections', () => {
    expect(template).toContain('<SystemSearchPanel>');
    expect(template).toContain('class="system-search-field"');
    expect(template).toContain('class="user-list-heading"');
    expect(template).toContain('class="user-list-panel"');
    expect(styles).toMatch(/\.user-manager-page\s*\{[\s\S]*grid-template-rows:\s*auto minmax\(0, 1fr\);/);
    expect(styles).toMatch(/\.user-list-panel\s*\{[\s\S]*min-width:\s*0;[\s\S]*overflow:\s*hidden;/);
    expect(styles).toMatch(/\.user-toolbar-actions\s*\{[\s\S]*justify-content:\s*flex-end;/);
    expect(styles).toMatch(/@media \(max-width:\s*920px\)[\s\S]*\.user-toolbar-actions\s*\{[\s\S]*flex-wrap:\s*wrap;/);
    expect(tableTemplate).toContain('class="user-table-scroll app-data-table-wrap"');
    expect(tableStyles).toMatch(/\.app-data-table-wrap\s*\{[\s\S]*overflow:\s*auto;/);
  });

  it('uses the koi-ui pagination layout directly below the user table', () => {
    expect(tableTemplate).toContain('class="user-table-scroll app-data-table-wrap"');
    expect(tableTemplate).toContain('class="app-data-table"');
    expect(tableTemplate).toContain('class="user-table-pagination host-pagination"');
    expect(tableTemplate).toContain('<AppPagination');
    expect(paginationTemplate).toContain('layout="total, sizes, prev, pager, next, jumper"');
    expect(paginationTemplate).toContain(':page-sizes="[10, 20, 50, 100, 200]"');
    expect(styles).toMatch(/\.user-table-pagination\s*\{[\s\S]*margin:\s*0 var\(--workspace-panel-padding\);/);
    expect(styles).not.toContain('.user-table .el-table {');
    expect(tableStyles).toContain('--app-table-section-gutter: var(--workspace-panel-padding, 16px);');
    expect(tableStyles).toMatch(/\.app-data-table-wrap\s*\{[\s\S]*padding:\s*0 var\(--app-table-section-gutter\) 2px;/);
    expect(tableStyles).toMatch(/\.app-data-table-wrap\s*\{[\s\S]*overflow:\s*auto;/);
    expect(tableStyles).toContain('--app-table-gutter: 8px;');
    expect(tableStyles).toMatch(/\.el-table\.app-data-table\s*\{[\s\S]*width:\s*calc\(100% - \(var\(--app-table-gutter\) \* 2\)\);[\s\S]*margin:\s*0 var\(--app-table-gutter\);[\s\S]*border:\s*1px solid var\(--ui-border\);/);
  });
});
