import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const componentSource = readFileSync(fileURLToPath(new URL('../RoleManager.vue', import.meta.url)), 'utf8');
const template = parseSfc(componentSource, { filename: 'RoleManager.vue' }).descriptor.template?.content ?? '';
const styles = readFileSync(fileURLToPath(new URL('../../../styles/tools/role-manager.css', import.meta.url)), 'utf8');
const tableStyles = readFileSync(fileURLToPath(new URL('../../../styles/base/data-table.css', import.meta.url)), 'utf8');

describe('RoleManager permission dialog', () => {
  it('uses the shared list toolbar layout for role management', () => {
    expect(template).toContain('class="role-list-heading"');
    expect(template).toContain('<SystemSearchPanel>');
    expect(template).toContain('class="system-search-field"');
    expect(template).toContain('请输入角色名称或标识');
    expect(styles).toMatch(/\.role-list-panel\s*\{[\s\S]*min-width:\s*0;/);
    expect(styles).toMatch(/\.role-list-toolbar\s*\{[\s\S]*border-bottom:\s*1px solid var\(--ui-border\);/);
    expect(styles).toMatch(/\.role-toolbar-actions\s*\{[\s\S]*flex-wrap:\s*wrap;/);
  });

  it('uses the shared login-log table presentation and an isolated scroll region', () => {
    expect(template).toContain('class="role-table-wrap app-data-table-wrap"');
    expect(template).toContain('class="role-table app-data-table"');
    expect(template).toContain('class="host-pagination"');
    expect(styles).not.toContain('.role-list-panel .el-table {');
    expect(styles).toMatch(/\.role-list-panel > \.host-pagination\s*\{[\s\S]*margin:\s*0 var\(--workspace-panel-padding\);/);
    expect(tableStyles).toContain('--app-table-section-gutter: var(--workspace-panel-padding, 16px);');
    expect(tableStyles).toMatch(/\.app-data-table-wrap\s*\{[\s\S]*padding:\s*0 var\(--app-table-section-gutter\) 2px;/);
    expect(tableStyles).toMatch(/\.app-data-table-wrap\s*\{[\s\S]*overflow:\s*auto;/);
    expect(tableStyles).toContain('--app-table-gutter: 8px;');
    expect(tableStyles).toMatch(/\.el-table\.app-data-table\s*\{[\s\S]*width:\s*calc\(100% - \(var\(--app-table-gutter\) \* 2\)\);[\s\S]*margin:\s*0 var\(--app-table-gutter\);[\s\S]*border:\s*1px solid var\(--ui-border\);/);
  });

  it('renders permissions as a three-column table with merged module cells', () => {
    expect(template).toContain('class="role-permission-table app-native-data-table"');
    expect(template).toContain(':rowspan="group.items.length"');
    expect(template).toContain('<th scope="col">模块</th>');
    expect(template).toContain('<th scope="col">页面</th>');
    expect(template).toContain('<th scope="col">功能权限</th>');
    expect(template).toContain('class="role-permission-summary"');
    expect(template).toContain("'role-permission-dialog': dialog?.mode === 'permissions' || dialog?.mode === 'view'");
    expect(styles).toMatch(/\.role-permission-table-wrap\s*\{[\s\S]*overflow:\s*hidden;/);
    expect(styles).toMatch(/\.role-permission-dialog\s*\{[\s\S]*width:\s*min\(1280px,\s*calc\(100vw\s*-\s*48px\)\)/);
    expect(styles).toMatch(/\.role-permission-table\s*\{[\s\S]*table-layout:\s*fixed;[\s\S]*border-collapse:\s*collapse;/);
    expect(styles).toMatch(/\.role-permission-actions\s*\{[\s\S]*grid-template-columns:\s*repeat\(3,\s*minmax\(100px,\s*1fr\)\);/);
  });

  it('keeps the permission table compact on narrow screens', () => {
    expect(styles).toMatch(/@media \(max-width:\s*720px\)[\s\S]*\.role-permission-actions\s*\{[\s\S]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(90px,\s*1fr\)\);/);
    expect(styles).toMatch(/\.role-permission-dialog\s*\{[\s\S]*max-height:\s*none;/);
    expect(styles).toMatch(/\.role-permission-dialog \.el-dialog__body\s*\{[\s\S]*overflow:\s*visible;/);
    expect(styles).toMatch(/\.role-permission-dialog \.popup-body\s*\{[\s\S]*overflow:\s*visible;/);
    expect(styles).toMatch(/\.role-feature-permissions\s*\{[\s\S]*grid-column:\s*1\s*\/\s*-1;[\s\S]*width:\s*100%;/);
  });
});
