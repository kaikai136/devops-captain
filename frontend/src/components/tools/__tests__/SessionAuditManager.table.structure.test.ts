import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const component = readFileSync(fileURLToPath(new URL('../SessionAuditManager.vue', import.meta.url)), 'utf8');
const auditStyles = readFileSync(fileURLToPath(new URL('../../../styles/tools/host/audit.css', import.meta.url)), 'utf8');
const sharedTableStyles = readFileSync(fileURLToPath(new URL('../../../styles/base/data-table.css', import.meta.url)), 'utf8');

describe('SessionAuditManager shared table presentation', () => {
  it('uses the shared table wrapper and presentation while preserving expandable rows', () => {
    expect(component).toContain('class="host-session-audit-table-wrap app-data-table-wrap"');
    expect(component).toContain('class="host-session-audit-table app-data-table"');
    expect(component).toContain('<el-table-column type="expand" width="48">');
    expect(auditStyles).toMatch(/\.host-session-audit-table\s*\{\s*min-width:\s*1420px;/);
    expect(auditStyles).not.toMatch(/\.host-session-audit-table\s*\{[^}]*border-top:/);
    expect(sharedTableStyles).toContain('.el-table.app-data-table th.el-table__cell');
    expect(sharedTableStyles).toContain('.el-table.app-data-table td.el-table__cell');
  });

  it('uses a large responsive viewport for readable operation recordings', () => {
    expect(component).toContain('class="host-session-recording-dialog"');
    expect(component).not.toContain('width="920px"');
    expect(auditStyles).toMatch(/\.host-session-recording-dialog\.el-dialog\s*\{[\s\S]*width:\s*min\(1280px, calc\(100vw - 48px\)\);[\s\S]*height:\s*min\(900px, calc\(100dvh - 24px\)\);/);
    expect(auditStyles).toMatch(/\.host-session-recording-dialog \.host-session-recording-player\s*\{[\s\S]*width:\s*100%;[\s\S]*height:\s*auto;/);
  });
});
