import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const source = readFileSync(fileURLToPath(new URL('../LoginYantrBackground.vue', import.meta.url)), 'utf8');
const styles = readFileSync(fileURLToPath(new URL('../../../../styles/auth-login.css', import.meta.url)), 'utf8');

describe('LoginYantrBackground', () => {
  it('implements the interactive particle and cursor-follow drawing loop', () => {
    expect(source).toContain('createRadialGradient');
    expect(source).toContain('ctx.lineTo(mx, my)');
    expect(source).toContain('ctx.arc(mouse.targetX, mouse.targetY');
    expect(source).toContain('window.requestAnimationFrame(animate)');
  });

  it('handles high-DPI resizing and lifecycle cleanup', () => {
    expect(source).toContain('Math.min(window.devicePixelRatio || 1, 2)');
    expect(source).toContain('context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)');
    expect(source).toContain('window.addEventListener(\'resize\', resizeHandler)');
    expect(source).toContain('window.removeEventListener(\'resize\', resizeHandler)');
    expect(source).toContain('window.cancelAnimationFrame(animationFrame)');
  });

  it('pauses for reduced motion and hidden documents', () => {
    expect(source).toContain("window.matchMedia('(prefers-reduced-motion: reduce)')");
    expect(source).toContain("document.addEventListener('visibilitychange', visibilityHandler)");
    expect(source).toContain('if (!pageVisible || reducedMotion) return;');
    expect(source).toContain('document.removeEventListener(\'visibilitychange\', visibilityHandler)');
  });

  it('keeps animated canvas content invalidating in Chromium compositing layers', () => {
    expect(styles).toMatch(/\.login-yantr-background\s*\{[\s\S]*backface-visibility:\s*hidden;/);
    expect(styles).toMatch(/\.login-yantr-background\s*\{[\s\S]*transform:\s*translateZ\(0\);/);
    expect(styles).toMatch(/\.login-yantr-background\s*\{[\s\S]*will-change:\s*contents;/);
  });
});
