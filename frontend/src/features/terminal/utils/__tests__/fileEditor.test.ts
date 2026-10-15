import { describe, expect, it } from 'vitest';
import { EditorState } from '@codemirror/state';
import { syntaxTree } from '@codemirror/language';
import { terminalFileLanguageExtension } from '../fileEditor';

describe('CodeMirror file languages', () => {
  it.each([
    ['app.js', 'const answer = 42;', 'Script'],
    ['app.ts', 'const answer: number = 42;', 'Script'],
    ['test.py', 'print(1)', 'Script'],
    ['config.json', '{"a": 1}', 'JsonText'],
  ])('parses %s with its language support', (name, doc, root) => {
    const state = EditorState.create({ doc, extensions: [terminalFileLanguageExtension(name)] });
    expect(syntaxTree(state).topNode.name).toBe(root);
  });
  it('keeps unknown extensions as plain text', () => {
    expect(terminalFileLanguageExtension('README.unknown')).toEqual([]);
  });
});
