import { readFileSync } from 'node:fs';
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc';
import * as ts from 'typescript';
import * as Vue from 'vue';
import { describe, expect, it, vi } from 'vitest';
import { navGroups } from '../../../app/navigation';

const source = readFileSync(new URL('../ApplicationKeyManager.vue', import.meta.url), 'utf8');
function setup(allowed = true) {
  const { descriptor } = parse(source);
  const script = compileScript(descriptor, { id: 'key-manager' });
  expect(compileTemplate({ source: descriptor.template!.content, filename: 'ApplicationKeyManager.vue', id: 'key-manager', compilerOptions: { bindingMetadata: script.bindings } }).errors).toEqual([]);
  const api = { listApplicationKeys: vi.fn().mockResolvedValue([]), createApplicationKey: vi.fn().mockResolvedValue({ id: 1 }), updateApplicationKey: vi.fn().mockResolvedValue({ id: 1 }), deleteApplicationKey: vi.fn().mockResolvedValue({ deleted: true }) };
  const require = (path: string) => path === 'vue' ? { ...Vue, onMounted: vi.fn() } : path === '@app/context' ? { useAppContext: () => ({ canUsePageAction: () => allowed }) } : path.endsWith('/applicationKeys') ? api : { errorMessage: String };
  const exports: any = {};
  new Function('require', 'exports', ts.transpileModule(script.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText)(require, exports);
  return { state: exports.default.setup({}, { expose: vi.fn() }), api };
}
const key = { id: 1, name: 'shared', username: 'db-user', hasPassword: true, connectionCount: 2, remark: 'production' };

describe('Application key management', () => {
  it('places the page immediately after the market and uses the account form layout without private keys', () => {
    const items = navGroups.find(group => group.key === 'market')!.items;
    expect(items[items.findIndex(item => item.key === 'applicationMarket') + 1].key).toBe('applicationKeys');
    expect(source).toContain('account-popup-form'); expect(source).toContain('label="密码" class="account-form-full"');
    expect(source).not.toContain('el-upload'); expect(source).not.toContain('privateKey');
    const styles = readFileSync(new URL('../../../styles/tools/account-manager.css', import.meta.url), 'utf8');
    expect(styles).toContain('repeat(2, minmax(0, 1fr))'); expect(styles).toContain('@media (max-width: 640px)');
    expect(styles).toContain('grid-template-columns: minmax(0, 1fr)');
  });
  it('creates with password whitespace preserved and edits with an empty password', async () => {
    const { state, api } = setup();
    state.openDialog(); state.form.value = { name: ' new ', username: ' user ', password: ' secret ', remark: '' };
    await state.saveKey(); expect(api.createApplicationKey).toHaveBeenCalledWith({ name: 'new', username: 'user', password: ' secret ', remark: '' });
    state.openDialog(key); expect(state.form.value.password).toBe('');
    await state.saveKey(); expect(api.updateApplicationKey).toHaveBeenCalledWith(1, expect.objectContaining({ password: '' }));
    state.openDialog(); expect(state.form.value).toEqual({ name: '', username: '', password: '', remark: '' });
    await state.saveKey(); expect(api.createApplicationKey).toHaveBeenCalledTimes(1);
  });
  it('searches, refreshes, removes and reports permission/error states', async () => {
    const { state, api } = setup(); api.listApplicationKeys.mockResolvedValue([key]);
    await state.loadKeys(); state.search.value = 'production'; expect(state.filtered.value).toHaveLength(1);
    state.search.value = 'missing'; expect(state.filtered.value).toEqual([]);
    state.confirmDelete.value = key;
    api.deleteApplicationKey.mockRejectedValueOnce(new Error('关联 2 个连接'));
    await state.removeKey(); expect(state.message.value).toContain('关联 2'); expect(state.confirmDelete.value).toEqual(key);
    await state.removeKey(); expect(state.confirmDelete.value).toBeNull();
    const denied = setup(false); denied.state.openDialog(); expect(denied.state.dialog.value).toBe(false);
    await denied.state.loadKeys(); await denied.state.saveKey(); expect(denied.api.listApplicationKeys).not.toHaveBeenCalled(); expect(denied.api.createApplicationKey).not.toHaveBeenCalled();
  });
  it('guards duplicate requests while saving', async () => {
    const { state, api } = setup(); state.openDialog(); state.form.value = { name: 'new', username: '', password: 'p', remark: '' };
    let finish!: (value: unknown) => void;
    api.createApplicationKey.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const pending = state.saveKey(); await state.saveKey(); expect(api.createApplicationKey).toHaveBeenCalledOnce();
    finish({ id: 1 }); await pending; expect(state.saving.value).toBe(false);
  });
});
