import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const component = readFileSync(new URL('../LockScreenOverlay.vue', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../../../styles/lock-screen.css', import.meta.url), 'utf8');

describe('reference lock screen integration', () => {
  it('uses two stages, shared authentication and the original menu entry', () => {
    expect(component).toContain('v-if="!showLogin"');
    expect(component).toContain('@keyup.stop="!showLogin && openLogin()"');
    expect(component).toContain('@click="openLogin"');
    expect(component).toContain('@submit.prevent="submit()"');
    expect(component).toContain('@click="submit()"');
    expect(component).toContain('@click="submit(true)"');
    expect(component).toContain('@click="back"');
    expect(component).toContain('value => props.unlockSession(value)');
    expect(component).not.toMatch(/waterfall|slider|beginDrag/);
  });

  it('recreates the reference display and keeps keyboard focus inside the lock screen', () => {
    expect(component).toContain(':size="128"');
    expect(component).toContain('请输入登录密码');
    expect(component).toContain('role="dialog" aria-modal="true"');
    expect(component).toContain('document.addEventListener(\'focusin\', keepFocus)');
    expect(component).toContain('document.removeEventListener(\'focusin\', keepFocus)');
    expect(component).toContain('event.key !== \'Tab\'');
    expect(styles).toContain('background: #000');
    expect(styles).toContain('backdrop-filter: blur(7px)');
    expect(styles).toContain('prefers-reduced-motion: reduce');
    expect(styles).toContain('lock-screen-charge-rotate');
  });
});
