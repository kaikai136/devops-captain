import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const template = readFileSync(fileURLToPath(new URL('../../UserManager.vue', import.meta.url)), 'utf8');
const tableTemplate = readFileSync(fileURLToPath(new URL('../UserTable.vue', import.meta.url)), 'utf8');
const styles = readFileSync(fileURLToPath(new URL('../../../../styles/tools/user-manager.css', import.meta.url)), 'utf8');

describe('UserManager layout', () => {
  it('keeps search and list actions in one responsive toolbar', () => {
    expect(template).not.toContain('class="user-filter-panel"');
    expect(template).toContain('class="user-list-heading"');
    expect(template).toContain('class="user-toolbar-search"');
    expect(styles).toMatch(/\.user-list-panel\s*\{[\s\S]*min-width:\s*0;[\s\S]*overflow:\s*hidden;/);
    expect(styles).toMatch(/\.user-toolbar-actions\s*\{[\s\S]*justify-content:\s*flex-end;/);
    expect(styles).toMatch(/@media \(max-width:\s*920px\)[\s\S]*\.user-toolbar-actions\s*\{[\s\S]*flex-wrap:\s*wrap;/);
    expect(styles).toMatch(/\.user-table-scroll\s*\{[\s\S]*overflow-x:\s*auto;/);
  });

  it('uses the koi-ui pagination layout directly below the user table', () => {
    expect(tableTemplate).toContain('class="user-table-scroll"');
    expect(tableTemplate).toContain('class="user-table-pagination"');
    expect(tableTemplate).toContain('layout="total, sizes, prev, pager, next, jumper"');
    expect(tableTemplate).toContain(':page-sizes="[10, 20, 50, 100, 200]"');
    expect(styles).toMatch(/\.user-table-scroll\s*\{[\s\S]*overflow-x:\s*auto;/);
    expect(styles).toMatch(/\.user-table-pagination\s*\{[\s\S]*margin:\s*0 8px;/);
  });
});
