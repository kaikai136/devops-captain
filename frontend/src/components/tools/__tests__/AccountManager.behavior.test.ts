import { readFileSync } from 'node:fs';
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc';
import * as ts from 'typescript';
import * as Vue from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';

const scopes: Vue.EffectScope[] = [];
afterEach(() => scopes.splice(0).forEach(scope => scope.stop()));
function setup(component = '../AccountManager.vue', props = {}) {
  const { descriptor } = parse(readFileSync(new URL(component, import.meta.url), 'utf8'));
  const script = compileScript(descriptor, { id: 'account-test' });
  expect(compileTemplate({ source: descriptor.template!.content, filename: component, id: 'account-test', compilerOptions: { bindingMetadata: script.bindings } }).errors).toEqual([]);
  const api = { createHostCredential: vi.fn().mockResolvedValue({ id: 1 }), updateHostCredential: vi.fn().mockResolvedValue({ id: 2 }) };
  const context = { hostCredentials: Vue.ref<any[]>([]), replaceHostCredential: vi.fn() };
  const require = (path: string) => path === 'vue' ? { ...Vue, onMounted: vi.fn() } : path === '@app/context' ? { useAppContext: () => context } : path.endsWith('/hostManagement') ? api : {};
  const js = ts.transpileModule(script.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const exports: any = {};
  new Function('require', 'exports', js)(require, exports);
  const scope = Vue.effectScope(); scopes.push(scope);
  const state: any = scope.run(() => exports.default.setup(props, { expose: vi.fn(), emit: vi.fn() }));
  return { state, api, context };
}

describe('Unified SSH accounts', () => {
  it('saves a password account with no private key or type, then resets new drafts', async () => {
    const { state, api } = setup();
    state.openCreateDialog(); state.form.value.name = 'password'; state.form.value.username = 'ops'; state.form.value.password = 'secret';
    await state.saveCredential();
    expect(api.createHostCredential).toHaveBeenCalledWith({ name: 'password', username: 'ops', password: 'secret', privateKeyName: '', privateKey: '', remark: '' });
    state.openCreateDialog(); expect(state.form.value.password).toBe('');
  });
  it('uploads, edits, searches and retains key account contents', async () => {
    const { state, api, context } = setup();
    const account = { id: 2, name: 'deploy', username: 'ops', password: '', privateKeyName: 'old', privateKey: 'old-key', remark: 'production' };
    context.hostCredentials.value = [account]; state.search.value = 'production';
    expect(state.filteredCredentials.value).toHaveLength(1); state.search.value = 'missing'; expect(state.filteredCredentials.value).toEqual([]);
    state.openEditDialog(account);
    await state.uploadPrivateKey({ raw: { name: 'id_key', text: async () => 'new-key' } });
    await state.saveCredential();
    expect(api.updateHostCredential).toHaveBeenCalledWith(2, expect.objectContaining({ username: 'ops', privateKeyName: 'id_key', privateKey: 'new-key', remark: 'production' }));
    expect(state.stats.value).toEqual({ total: 1, withPassword: 0, withKey: 1 });
  });
  it('offers every account in the host credential selector', () => {
    const credentials = [{ id: 1, name: 'previous-app', username: 'ops' }, { id: 2, name: 'host', username: 'root' }];
    const { state } = setup('../../../features/hosts/components/CredentialSelector.vue', { credentials, modelValue: null });
    expect(state.hostCredentials.value).toEqual(credentials);
  });
});
