import { readFileSync } from 'node:fs';
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc';
import * as ts from 'typescript';
import * as Vue from 'vue';
import { afterEach, describe, expect, it, vi } from 'vitest';
import * as connectionUtils from '../utils/mysqlConnection';
import { buildDatabaseTreeMenu } from '../components/databaseTreeMenu';
import type { DatabaseAsset } from '../api/databaseManagement';
import { keyHarness } from './applicationKeyHarness';

const scopes: Vue.EffectScope[] = [];
afterEach(() => { scopes.splice(0).forEach(scope => scope.stop()); });
function setup(props: Record<string, unknown> = {}, component = 'MysqlConnectionDialog') {
  const { descriptor } = parse(readFileSync(new URL(`../components/${component}.vue`, import.meta.url), 'utf8'));
  const script = compileScript(descriptor, { id: component });
  const rendered = compileTemplate({ source: descriptor.template!.content, filename: component, id: component, compilerOptions: { bindingMetadata: script.bindings } });
  expect(rendered.errors).toEqual([]);
  const api = { createDatabaseAsset: vi.fn().mockResolvedValue({ id: 8 }), updateDatabaseAsset: vi.fn().mockResolvedValue({ id: 7 }), testDatabaseConnection: vi.fn().mockResolvedValue({ ok: true, message: 'ok', databases: ['tele'], elapsedMs: 12 }) };
  const emit = vi.fn();
  const querySelector = vi.fn().mockReturnValue({ scrollIntoView: vi.fn(), querySelector: () => ({ focus: vi.fn() }) });
  const exports: any = {};
  const keys = keyHarness({ canUsePageAction: () => true });
  const require = (path: string) => path === 'vue' ? Vue : path.endsWith('/useApplicationKeyChoices') ? keys.choices : path.endsWith('/mysqlConnection') ? connectionUtils : path.endsWith('/databaseManagement') ? api : path.endsWith('/errors') ? { errorMessage: String } : {};
  const js = ts.transpileModule(script.content, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  new Function('require', 'exports', 'document', js)(require, exports, { querySelector });
  const scope = Vue.effectScope(); scopes.push(scope);
  const state: any = scope.run(() => exports.default.setup({ canTest: true, canSave: true, ...props }, { expose: vi.fn(), emit }));
  return { state, api, emit, querySelector };
}
const asset = { id: 7, name: 'mysql', dbType: 'mysql', host: 'db.test', port: 3306, username: 'user', options: {}, connectionSecretStatus: { sslCa: { configured: true, name: 'old.pem' }, sshPassword: { configured: true } } } as DatabaseAsset;
function valid(state: any) { state.form.name = 'draft'; state.form.username = 'user'; state.form.host = 'db.test'; }

describe('MySQL connection dialog', () => {
  it('starts each new connection with empty identity fields and keeps protocol defaults', () => {
    const first = setup().state;
    expect(first.form).toMatchObject({ name: '', host: '', username: '', password: '', databaseName: '', port: 3306 });
    first.form.name = 'previous'; first.form.host = 'previous.test'; first.form.password = 'previous';
    expect(setup().state.form).toMatchObject({ name: '', host: '', username: '', password: '', databaseName: '', port: 3306 });
  });
  it('preserves draft settings across tabs without mutating the asset and reopens on general', () => {
    const { state } = setup({ asset: Vue.reactive(asset) });
    state.form.name = 'draft'; state.activeTab.value = 'advanced'; state.options.ssh.enabled = true;
    state.activeTab.value = 'ssl'; state.options.ssl = true; state.activeTab.value = 'general';
    expect(state.form.name).toBe('draft'); expect(state.options.ssh.enabled).toBe(true);
    expect(asset.name).toBe('mysql'); expect(asset.options).toEqual({});
    expect(setup({ asset }).state.activeTab.value).toBe('general');
  });
  it('preserves or explicitly clears editing passwords without linked credentials', async () => {
    const { state, api } = setup({ asset });
    expect(state.payload()).not.toHaveProperty('password');
    expect(state.form.username).toBe('user'); expect(state.form.password).toBe('');
    state.options.authMethod = 'none'; await state.save();
    expect(api.updateDatabaseAsset).toHaveBeenCalledWith(7, expect.objectContaining({ options: expect.objectContaining({ authMethod: 'none' }) }));
    expect(api.testDatabaseConnection).not.toHaveBeenCalled();
  });
  it('preserves manual drafts while key mode submits only its reference', async () => {
    const { state, api } = setup(); valid(state);
    state.form.password = ' manual password ';
    state.options.authMethod = 'applicationKey';
    await state.loadKeys(); state.form.applicationKeyId = 5;
    expect(state.selectedKey.value.username).toBe('key-user');
    await state.save();
    expect(api.createDatabaseAsset).toHaveBeenCalledWith(expect.objectContaining({ applicationKeyId: 5, username: '' }));
    expect(api.createDatabaseAsset.mock.calls[0][0]).not.toHaveProperty('password');
    state.options.authMethod = 'password';
    expect(state.payload()).toMatchObject({ applicationKeyId: null, username: 'user', password: ' manual password ' });
    state.options.authMethod = 'applicationKey'; state.form.applicationKeyId = 6;
    expect(await state.validate()).toBe(false);
    expect(state.errors.value.applicationKey).toBeTruthy();
  });
  it('shows the existing key when editing and requires reselection after import', async () => {
    const linked = { ...asset, applicationKeyId: 12, applicationKeyName: 'linked', username: 'linked-user', options: { authMethod: 'applicationKey' } };
    const { state } = setup({ asset: linked });
    expect(state.selectedKey.value).toMatchObject({ id: 12, name: 'linked', username: 'linked-user' });
    expect(await state.validate()).toBe(true);
    expect(await setup({ asset: { ...linked, applicationKeyId: null } }).state.validate()).toBe(false);
  });
  it('tests an unsaved draft, lists databases, and blocks duplicate test/save calls', async () => {
    const { state, api } = setup(); valid(state);
    let finish!: (value: unknown) => void;
    api.testDatabaseConnection.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    const pending = state.test(); await Vue.nextTick();
    await state.save(); await state.test(); expect(api.testDatabaseConnection).toHaveBeenCalledOnce(); expect(api.createDatabaseAsset).not.toHaveBeenCalled();
    expect(state.testing.value).toBe(true); expect(state.saving.value).toBe(false);
    finish({ ok: true, message: 'ok', databases: ['tele'], elapsedMs: 12 }); await pending;
    expect(state.databases.value).toEqual(['tele']); expect(state.testing.value).toBe(false);
    await Promise.all([state.save(), state.save()]); expect(api.createDatabaseAsset).toHaveBeenCalledOnce();
  });
  it('routes validation to the first invalid tab and focuses that field', async () => {
    const { state, api, querySelector } = setup(); valid(state); state.activeTab.value = 'ssl'; state.options.connectTimeout = 0;
    await state.save(); expect(state.activeTab.value).toBe('advanced'); expect(querySelector.mock.calls[0][0]).toContain('timeout'); expect(api.createDatabaseAsset).not.toHaveBeenCalled();
    state.options.connectTimeout = 5; state.options.ssl = true; state.options.tls.mode = 'verify_ca';
    await state.save(); expect(state.activeTab.value).toBe('ssl'); expect(state.errors.value.sslCa).toBeTruthy();
  });
  it('retains SSH authentication drafts and SSL file status, replacement and removal', async () => {
    const { state } = setup({ asset });
    state.setSecret('sshPassword', 'jump'); state.options.ssh.authMethod = 'privateKey'; state.options.ssh.authMethod = 'password';
    expect(state.form.connectionSecrets.sshPassword).toBe('jump');
    expect(state.fileName('sslCa')).toBe('old.pem'); expect(state.payload().connectionSecrets).not.toHaveProperty('sslCa');
    state.setSecret('sslCa', { name: 'new.pem', content: 'PEM' }); state.options.ssl = false; state.activeTab.value = 'general'; state.options.ssl = true;
    expect(state.fileName('sslCa')).toBe('new.pem');
    state.setSecret('sslCa', null); expect(state.hasSecret('sslCa')).toBe(false); expect(state.payload().connectionSecrets.sslCa).toBeNull();
  });
  it('adds each allowed parameter once and serializes local expiry with a timezone', () => {
    const { state } = setup(); for (let i = 0; i < 6; i++) state.addParameter();
    expect(state.parameters.value).toHaveLength(5); expect(new Set(state.parameters.value.map((row: any) => row.key)).size).toBe(5);
    state.expiry.value = new Date('2030-01-02T03:04:05+08:00');
    expect(state.payload().options.expiresAt).toBe('2030-01-01T19:04:05.000Z');
    state.expiry.value = null; expect(state.payload().options.expiresAt).toBeNull();
  });
  it('blocks requests without edit/create or test permission', async () => {
    for (const rights of [{ canSave: false }, { canTest: false }]) {
      const { state, api } = setup(rights); valid(state); await state.test(); expect(api.testDatabaseConnection).not.toHaveBeenCalled();
      if (!('canTest' in rights)) { await state.save(); expect(api.createDatabaseAsset).not.toHaveBeenCalled(); }
    }
  });
  it('rejects oversized and malformed files without replacing the existing draft', async () => {
    const { state, emit } = setup({ label: 'CA' }, 'ConnectionFileField');
    await state.choose({ target: { files: [{ size: 256 * 1024 + 1 }], value: 'x' } }); expect(emit.mock.calls[0][0]).toBe('error');
    await state.choose({ target: { files: [{ size: 1, text: async () => 'invalid' }], value: 'x' } }); expect(emit).not.toHaveBeenCalledWith('change', expect.anything());
    await state.choose({ target: { files: [{ size: 1, name: 'ca.pem', text: async () => '-----BEGIN CERTIFICATE-----' }], value: 'x' } });
    expect(emit).toHaveBeenCalledWith('change', { name: 'ca.pem', content: '-----BEGIN CERTIFICATE-----' });
  });
  it('handles unreadable files and ignores file selection when disabled', async () => {
    const file = { size: 1, text: vi.fn().mockRejectedValue(new Error('unreadable')) };
    const { state, emit } = setup({ label: 'CA' }, 'ConnectionFileField');
    await state.choose({ target: { files: [file], value: 'x' } });
    expect(emit).toHaveBeenCalledWith('error', '无法读取文件，请重新选择');
    expect(emit).not.toHaveBeenCalledWith('change', expect.anything());
    file.text.mockClear();
    await setup({ label: 'CA', disabled: true }, 'ConnectionFileField').state.choose({ target: { files: [file], value: 'x' } });
    expect(file.text).not.toHaveBeenCalled();
  });
  it('keeps readonly exports enabled and disables writes and expired operations', () => {
    const readonly = { ...asset, options: { readOnly: true } };
    const context = { connected: true, dbType: 'mysql', capabilities: ['accounts'], selectedCount: 0, pinned: false, can: (action: string) => connectionUtils.connectionCan(readonly, action), run: vi.fn() };
    const entries = buildDatabaseTreeMenu({ kind: 'database', name: 'tele' }, context);
    expect(entries.find(item => item.id === 'database-export')?.enabled).toBe(true);
    for (const id of ['database-import', 'new-table', 'edit-database', 'delete-database']) expect(entries.find(item => item.id === id)?.enabled).toBe(false);
    expect(connectionUtils.connectionCan({ ...asset, options: { expiresAt: '2000-01-01T00:00:00Z' } }, 'view_data')).toBe(false);
    expect(connectionUtils.connectionCan({ ...asset, options: { expiresAt: '2000-01-01T00:00:00Z' } }, 'edit')).toBe(true);
  });
});
