import { readFileSync } from 'node:fs';
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../components/DatabaseTransferCenter.vue', import.meta.url), 'utf8');
const { descriptor } = parse(source);
const script = descriptor.scriptSetup!.content;
const template = descriptor.template!.content;
const panel = template.slice(template.indexOf('<section class="transfer-message-panel"'));

describe('read-only transfer messages', () => {
  it('compiles with Element Plus and keeps the notification entry', () => {
    const compiledScript = compileScript(descriptor, { id: 'transfer-center' });
    const result = compileTemplate({ source: template, filename: 'DatabaseTransferCenter.vue', id: 'transfer-center', compilerOptions: { bindingMetadata: compiledScript.bindings } });
    expect(result.errors).toEqual([]);
    expect(template).toContain('aria-label="任务消息"');
    expect(template).toContain('v-model:visible="popoverVisible"');
  });

  it('renders all task information without interactive controls or actions', () => {
    expect(panel).toContain('v-for="task in tasks"');
    expect(panel).toContain('statusLabel(task.status)');
    expect(panel).toContain('task.progress');
    expect(panel).toContain('task.error');
    expect(panel).toContain('task.preview.warnings');
    expect(panel).toContain('previewObjects(task)');
    expect(panel).toContain('task.createdAt');
    expect(panel).toContain('task.expiresAt');
    expect(panel).toContain('暂无导入导出任务');
    expect(panel).not.toMatch(/<el-(?:button|select|option|input)\b|<a\b|@(?:click|change|submit)|v-model/);
  });

  it('removes task action handlers while retaining automatic updates and cleanup', () => {
    for (const action of ['confirmDatabaseTransfer', 'cancelDatabaseTransfer', 'retryDatabaseTransfer', 'deleteDatabaseTransfer', 'databaseTransferDownloadUrl', 'ElMessageBox']) {
      expect(script).not.toContain(action);
    }
    expect(script).toContain('listDatabaseTransferTasks()');
    expect(script).toContain('socket.onmessage');
    expect(script).toContain('if (open) void refresh()');
    expect(script).toContain('window.setInterval');
    expect(script).toContain('clearInterval(pollTimer)');
    expect(script).toContain('closeSocket()');
    expect(script).toContain("window.removeEventListener('database-transfer:upload'");
  });
});
