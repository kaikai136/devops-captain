import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const shell = readFileSync(new URL('../base/shell-nav.css', import.meta.url), 'utf8');
const tokens = readFileSync(new URL('../base/element-plus-theme.css', import.meta.url), 'utf8');
const dark = readFileSync(new URL('../dark-mode.css', import.meta.url), 'utf8');
const popup = readFileSync(new URL('../base/popup-system.css', import.meta.url), 'utf8');

describe('dark mode palette coverage', () => {
  it('overrides navigation and active items without white backgrounds', () => {
    expect(shell).toContain('.workspace-dark .workspace-nav-menu .el-menu-item.is-active');
    expect(shell).toContain('background: var(--workspace-surface);');
  });

  it('maps Element Plus tables, cards, and fields to workspace dark tokens', () => {
    expect(tokens).toContain('--el-table-bg-color: var(--workspace-surface)');
    expect(tokens).toContain('--el-fill-color-blank: var(--workspace-surface)');
    expect(dark).toContain('.workspace-dark :where(.el-table');
    expect(dark).toContain('background-color: var(--dark-field-bg)');
  });

  it('themes teleported popups and semantic tag backgrounds', () => {
    expect(popup).toContain('--popup-surface: var(--ui-popover)');
    expect(popup).toContain('--popup-text: var(--ui-foreground)');
    for (const color of ['success', 'warning', 'danger', 'info']) {
      expect(tokens).toContain(`--el-color-${color}-light-9: color-mix(in srgb, var(--el-color-${color}) 10%, var(--ui-card))`);
    }
  });

  it('does not override Element Plus primary and danger buttons with legacy native button styles', () => {
    const header = readFileSync(new URL('../base/workspace-header.css', import.meta.url), 'utf8');
    expect(header).toContain('.workspace-dark button:not(.el-button):not(.primary)');
    expect(dark).toContain('button:not(.el-button):not(.primary):not(.danger):not(:disabled)');
  });

  it.each([
    'account-manager.css', 'application-market.css', 'authenticator.css', 'bulk-execution.css',
    'dashboard.css', 'device-manager.css', 'host/table.css', 'host/layout-groups.css',
    'host/quick-commands.css', 'ip-scanner.css', 'login-log-manager.css', 'password-generator.css',
    'profile-center.css', 'role-manager.css', 'security-scan.css', 'subnet-calculator.css',
    'system-settings.css', 'user-manager.css',
  ])('uses shared surface and text tokens in %s', file => {
    const source = readFileSync(new URL(`../tools/${file}`, import.meta.url), 'utf8');
    expect(source).toMatch(/var\(--ui-(?:card|muted|foreground|border)/);
    expect(source).not.toMatch(/background(?:-color)?:\s*(?:#fff(?:fff)?|white)\s*;/i);
    expect(source).not.toMatch(/color:\s*#(?:173252|102945|111827)\s*;/i);
    const panels = source.replace(/[^{}]*watermark[^{}]*\{[^{}]*\}/g, '');
    expect(panels).not.toMatch(/background:\s*rgba\(255,\s*255,\s*255,/);
  });
});
