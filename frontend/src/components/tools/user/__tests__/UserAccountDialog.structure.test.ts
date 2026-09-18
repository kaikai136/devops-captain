import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const component = readFileSync(fileURLToPath(new URL('../UserAccountDialog.vue', import.meta.url)), 'utf8');
const styles = readFileSync(fileURLToPath(new URL('../../../../styles/tools/user-manager.css', import.meta.url)), 'utf8');

describe('UserAccountDialog layout', () => {
  it('keeps the account form within the dialog without horizontal overflow', () => {
    expect(component).toContain('class="user-form-modal popup-body popup-form-grid"');
    expect(styles).toMatch(/\.user-form-modal\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\);[\s\S]*width:\s*100%;[\s\S]*max-width:\s*100%;/);
    expect(styles).toMatch(/\.user-form-dialog \.el-dialog__body\s*\{[\s\S]*overflow-x:\s*hidden;/);
    expect(styles).toMatch(/\.user-role-line\s*\{[\s\S]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto;/);
    expect(styles).not.toMatch(/\.user-form-note\s*\{[\s\S]*margin:\s*0\s+0\s+0\s+164px/);
    expect(styles).not.toMatch(/\.user-password-meter\s*\{[\s\S]*width:\s*380px/);
  });
});
