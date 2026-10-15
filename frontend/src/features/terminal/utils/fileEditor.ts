import { javascript } from '@codemirror/lang-javascript';
import { json } from '@codemirror/lang-json';
import { python } from '@codemirror/lang-python';
import { html } from '@codemirror/lang-html';
import { css } from '@codemirror/lang-css';
import { markdown } from '@codemirror/lang-markdown';
import { sql } from '@codemirror/lang-sql';
import type { Extension } from '@codemirror/state';

const languageExtensions: Record<string, () => Extension> = {
  js: () => javascript(), mjs: () => javascript(), cjs: () => javascript(),
  jsx: () => javascript({ jsx: true }), ts: () => javascript({ typescript: true }),
  tsx: () => javascript({ typescript: true, jsx: true }),
  json: () => json(), jsonc: () => json(), py: () => python(), html: () => html(), htm: () => html(),
  css: () => css(), scss: () => css(), less: () => css(), md: () => markdown(), markdown: () => markdown(), sql: () => sql(),
};

export function terminalFileLanguageExtension(filename: string): Extension {
  const extension = filename.toLowerCase().split('.').pop() || '';
  try {
    return languageExtensions[extension]?.() ?? [];
  } catch {
    return [];
  }
}
