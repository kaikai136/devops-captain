import { readFileSync } from 'node:fs';
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../components/DatabaseConnectionDialog.vue', import.meta.url), 'utf8');

describe('database connection dialog', () => {
  it('compiles its unified connection form', () => {
    const { descriptor, errors } = parse(source);
    expect(errors).toEqual([]);
    const script = compileScript(descriptor, { id: 'database-connection-dialog' });
    const template = compileTemplate({ source: descriptor.template!.content, filename: 'DatabaseConnectionDialog.vue', id: 'database-connection-dialog', compilerOptions: { bindingMetadata: script.bindings } });
    expect(template.errors).toEqual([]);
  });

  it('exposes the shared type-specific fields and preserves edit credentials', () => {
    expect(source).toContain('连接超时（秒）');
    expect(source).toContain('SID / Service Name');
    expect(source).toContain('Redis DB 编号');
    expect(source).toContain('留空保持原密码');
    expect(source).toContain("emit('save', payload())");
    expect(source).toContain('testDatabaseConnection');
  });
});
