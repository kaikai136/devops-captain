import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { parse as parseSfc } from '@vue/compiler-sfc';
import { describe, expect, it } from 'vitest';

function readSource(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(`../${relativePath}`, import.meta.url)), 'utf8');
}

function template(relativePath: string) {
  return parseSfc(readSource(relativePath), { filename: relativePath }).descriptor.template?.content ?? '';
}

describe('login page Element Plus structure', () => {
  it('uses Element Plus controls for login inputs and actions', () => {
    const loginPage = template('components/auth/LoginPage.vue');
    const loginForm = template('components/auth/login/LoginFormCard.vue');

    for (const source of [loginPage, loginForm]) {
      expect(source).toContain('<el-');
      expect(source).not.toMatch(/<(button|select|textarea)\b/);
      expect(source).not.toMatch(/<input(?![^>]*hidden)/);
    }

    expect(loginForm).toContain('class="login-field"');
    expect(loginForm).toContain('<template #prefix>');
    expect(loginForm).not.toContain('login-input-wrapper');
  });

  it('keeps login popovers and form fields inside viewport-safe bounds', () => {
    const loginPage = readSource('components/auth/LoginPage.vue');
    const styles = readSource('styles/auth-login.css');
    const colorOptionsLine = loginPage.match(/const colorOptions = \[(.*?)\];/s)?.[1] ?? '';

    expect(loginPage).toContain("color: '#2563EB'");
    expect(colorOptionsLine).not.toContain('#8B5CF6');
    expect(styles).toContain('--login-accent: #2563eb');
    expect(styles).toContain('max-height: calc(100dvh - 76px)');
    expect(styles).toContain('.login-field .el-input__wrapper');
    expect(styles).toContain('.login-custom-color .el-input__wrapper');
    expect(styles).not.toContain('.login-input-wrapper input');
    expect(styles).not.toContain('.login-password-toggle');
  });

  it('keeps Element Plus login input interiors visually continuous', () => {
    const styles = readSource('styles/auth-login.css');

    expect(styles).toContain('.login-field .el-input__inner');
    expect(styles).toContain('background: transparent');
    expect(styles).toContain('.login-field .el-input__inner:-webkit-autofill');
    expect(styles).toContain('-webkit-text-fill-color: var(--login-text)');
    expect(styles).toContain('caret-color: var(--login-text)');
  });

  it('only switches directly between Koi UI and glass login modes', () => {
    const loginPage = readSource('components/auth/LoginPage.vue');
    const loginTemplate = template('components/auth/LoginPage.vue');

    expect(loginPage).toContain("type LoginLayoutKey = 'koi' | 'glass';");
    expect(loginPage).toContain("appearance.value.layout === 'koi' ? 'glass' : 'koi'");
    expect(loginTemplate).toContain('@click="toggleLayout"');
    expect(loginTemplate).not.toContain("activePanel === 'layout'");
    expect(loginTemplate).not.toContain('login-layout-choice');
  });
});
