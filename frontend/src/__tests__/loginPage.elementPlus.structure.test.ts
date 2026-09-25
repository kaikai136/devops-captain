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
    expect(loginPage).not.toContain('colorOptions');
    expect(loginPage).not.toContain('customColor');
    expect(loginPage).not.toContain('login-custom-color');
    expect(styles).not.toContain('--login-accent: #2563eb');
    expect(styles).toContain('max-height: calc(100dvh - 76px)');
    expect(styles).toContain('.login-field .el-input__wrapper');
    expect(styles).not.toContain('.login-custom-color .el-input__wrapper');
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

  it('uses the Yantr canvas background without the legacy shape layer', () => {
    const loginPage = readSource('components/auth/LoginPage.vue');
    const loginTemplate = template('components/auth/LoginPage.vue');
    const styles = readSource('styles/auth-login.css');
    const background = readSource('components/auth/login/LoginYantrBackground.vue');

    expect(loginPage).toContain("import LoginYantrBackground from './login/LoginYantrBackground.vue';");
    expect(loginTemplate).toContain('<LoginYantrBackground :dark="effectiveDark" />');
    expect(loginTemplate).not.toContain('login-bg-grid');
    expect(loginTemplate).not.toContain('login-bg-shape');
    expect(background).toContain('requestAnimationFrame');
    expect(background).toContain('devicePixelRatio');
    expect(background).toContain('prefers-reduced-motion');
    expect(background).toContain('visibilitychange');
    expect(background).toContain('window.removeEventListener');
    expect(styles).toContain('.login-yantr-background');
    expect(styles).toContain('pointer-events: none');
  });
});
