import { readFileSync } from 'node:fs';
import { compileScript, compileTemplate, parse } from '@vue/compiler-sfc';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../components/DatabaseExportDialog.vue', import.meta.url), 'utf8');
const { descriptor } = parse(source);
const template = descriptor.template!.content;
const script = descriptor.scriptSetup!.content;

describe('database export configuration', () => {
  it('compiles and keeps searchable multi-table selection defaulted to all tables', () => {
    const compiled = compileScript(descriptor, { id: 'database-export-dialog' });
    expect(compileTemplate({ source: template, filename: 'DatabaseExportDialog.vue', id: 'database-export-dialog', compilerOptions: { bindingMetadata: compiled.bindings } }).errors).toEqual([]);
    expect(template).toContain('multiple filterable');
    expect(script).toContain('selected.value = target.table ? tables.value.filter(name => name === target.table) : [...tables.value]');
    expect(template).toContain('selected = [...tables]');
    expect(template).toContain('selected = []');
  });

  it('selects a destination before dispatching task creation and exposes SQL options', () => {
    expect(script.indexOf('await chooseExportDestination(payload.fileName)')).toBeLessThan(script.indexOf("window.dispatchEvent(new CustomEvent('database-export:start'"));
    for (const option of ['continueOnError', 'batchInsert', 'upsert', 'dropTable']) expect(script).toContain(option);
    for (const label of ['发生错误继续执行', '批量语句', '主键存在则更新', '表结构', '表数据', 'Drop Table If Exists']) expect(template).toContain(label);
  });

  it('preserves schema selection, permissions, validation, and user cancellation', () => {
    expect(script).toContain("format.value !== 'sql' || structure.value || data.value");
    expect(script).toContain("canStructure");
    expect(script).toContain("if ((error as DOMException).name !== 'AbortError')");
    expect(template).toContain('重新读取表清单');
  });
});
