import { parse as parseSfc } from '@vue/compiler-sfc';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function readComponent(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(`../${relativePath}`, import.meta.url)), 'utf8');
}

function template(relativePath: string) {
  return parseSfc(readComponent(relativePath), { filename: relativePath }).descriptor.template?.content ?? '';
}

describe('system pages use Element Plus widgets', () => {
  it('renders the user manager with Element Plus controls', () => {
    const userManager = template('components/tools/UserManager.vue');
    const userTable = template('components/tools/user/UserTable.vue');
    const userAccountDialog = template('components/tools/user/UserAccountDialog.vue');
    const resetPasswordDialog = template('components/tools/user/UserResetPasswordDialog.vue');
    const deleteDialog = template('components/tools/user/UserDeleteDialog.vue');
    const resetTwoFactorDialog = template('components/tools/user/UserResetTwoFactorDialog.vue');

    for (const source of [userManager, userTable, userAccountDialog, resetPasswordDialog, deleteDialog, resetTwoFactorDialog]) {
      expect(source).toContain('<el-');
    }

    expect(userManager).not.toContain('<input');
    expect(userManager).not.toContain('<button');
    expect(userTable).not.toContain('<select');
    expect(userAccountDialog).not.toContain('<input');
    expect(resetPasswordDialog).not.toContain('<input');
  });

  it('renders the log and role pages with Element Plus controls', () => {
    const loginLogs = template('components/tools/LoginLogManager.vue');
    const operationLogs = template('components/tools/OperationLogManager.vue');
    const roles = template('components/tools/RoleManager.vue');
    const sessions = template('components/tools/SessionAuditManager.vue');

    for (const source of [loginLogs, operationLogs, roles, sessions]) {
      expect(source).toContain('<el-');
    }

    expect(loginLogs).not.toContain('<input');
    expect(operationLogs).not.toContain('<input');
    expect(roles).not.toContain('<input');
    expect(sessions).not.toContain('<input');
  });

  it('uses one shared search panel across system management pages', () => {
    const searchPanel = readComponent('shared/components/SystemSearchPanel.vue');
    const systemPages = [
      'components/tools/UserManager.vue',
      'components/tools/RoleManager.vue',
      'components/tools/LoginLogManager.vue',
      'components/tools/OperationLogManager.vue',
    ];

    for (const relativePath of systemPages) {
      const source = template(relativePath);
      expect(source, relativePath).toContain('<SystemSearchPanel');
      expect(source, relativePath).toContain('class="system-search-form"');
      expect(source, relativePath).toContain('class="system-search-actions"');
    }

    expect(searchPanel).toContain('class="system-search-panel-body"');
    expect(searchPanel).not.toContain('<button');
    expect(searchPanel).not.toContain('expanded');
  });

  it('renders the network utility pages with Element Plus controls', () => {
    const ipScanner = template('components/tools/IpScanner.vue');
    const pingProbe = template('components/tools/machine/PingProbe.vue');
    const portScanner = template('components/tools/machine/PortScanner.vue');
    const subnetCalculator = template('components/tools/SubnetCalculator.vue');
    const passwordGenerator = template('components/tools/PasswordGenerator.vue');

    for (const source of [ipScanner, pingProbe, portScanner, subnetCalculator, passwordGenerator]) {
      expect(source).toContain('<el-');
      expect(source).not.toMatch(/<(input|button|select|textarea)\b/);
    }
  });

  it('renders the remaining tool pages with Element Plus controls', () => {
    const authenticator = template('components/tools/AuthenticatorPanel.vue');
    const profileCenter = template('components/tools/ProfileCenter.vue');
    const securityScan = template('components/tools/SecurityScanPanel.vue');

    for (const source of [authenticator, profileCenter, securityScan]) {
      expect(source).toContain('<el-');
      expect(source).not.toMatch(/<(button|select|textarea)\b/);
    }

    expect(authenticator).not.toMatch(/<input(?![^>]*hidden)/);
    expect(profileCenter).not.toMatch(/<input(?![^>]*hidden)/);
    expect(securityScan).not.toMatch(/<input(?![^>]*hidden)/);
  });

  it('renders the application market with Element Plus controls', () => {
    const applicationMarket = template('features/application-market/components/ApplicationMarketPanel.vue');

    expect(applicationMarket).toContain('<el-');
    expect(applicationMarket).not.toMatch(/<(input|button|select|textarea)\b/);
  });

  it('renders the bulk execution panel with Element Plus controls', () => {
    const bulkExecution = template('features/bulk-execution/components/BulkExecutionPanel.vue');

    expect(bulkExecution).toContain('<el-');
    expect(bulkExecution).not.toMatch(/<(button|select|textarea)\b/);
    expect(bulkExecution).not.toMatch(/<input(?![^>]*hidden)/);
  });

  it('uses the shared user-management table style on every data table', () => {
    const tableComponents = [
      'components/tools/AccountManager.vue',
      'components/tools/LoginLogManager.vue',
      'components/tools/OperationLogManager.vue',
      'components/tools/PasswordGenerator.vue',
      'components/tools/RoleManager.vue',
      'components/tools/SecurityScanPanel.vue',
      'components/tools/SessionAuditManager.vue',
      'components/tools/SubnetCalculator.vue',
      'components/tools/machine/PingProbe.vue',
      'components/tools/user/UserTable.vue',
      'features/bulk-execution/components/BulkExecutionPanel.vue',
      'features/company/components/DeviceManager.vue',
      'features/hosts/components/HostImportDialog.vue',
    ];

    for (const relativePath of tableComponents) {
      const source = template(relativePath);
      const tableTags = source.match(/<el-table(?!-)\b[^>]*>/g) ?? [];

      expect(tableTags.length, relativePath).toBeGreaterThan(0);
      for (const tableTag of tableTags) {
        expect(tableTag, relativePath).toContain('app-data-table');
      }
    }

    expect(template('features/hosts/components/HostTable.vue')).toContain('class="host-table app-data-grid"');
    expect(template('components/tools/RoleManager.vue')).toContain('class="role-permission-table app-native-data-table"');
  });

  it('uses one shared width container for the management log tables', () => {
    for (const relativePath of ['components/tools/LoginLogManager.vue', 'components/tools/OperationLogManager.vue']) {
      expect(template(relativePath), relativePath).toContain('class="login-log-table-wrap app-data-table-wrap"');
    }
  });
});
