import { readFileSync } from 'node:fs';
import * as ts from 'typescript';
import * as Vue from 'vue';
import { vi } from 'vitest';

export function keyHarness(context: { canUsePageAction: (...args: any[]) => boolean }, mounted: (() => unknown)[] = []) {
  const api = { selectApplicationKeys: vi.fn().mockResolvedValue([{ id: 5, name: 'shared', username: 'key-user' }, { id: 6, name: 'redis', username: '' }]) };
  const exports: any = {};
  const source = readFileSync(new URL('../composables/useApplicationKeyChoices.ts', import.meta.url), 'utf8');
  const require = (path: string) => path === 'vue' ? { ...Vue, onMounted: (fn: () => unknown) => mounted.push(fn) } : path === '@app/context' ? { useAppContext: () => context } : path.endsWith('/applicationKeys') ? api : { errorMessage: String };
  new Function('require', 'exports', ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText)(require, exports);
  return { choices: exports, api };
}
