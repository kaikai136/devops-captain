import { describe, expect, it } from 'vitest';
import { folderUploadItems } from '../folderUpload';

function file(name: string, webkitRelativePath: string) {
  return { name, webkitRelativePath } as File;
}

describe('folder upload paths', () => {
  const files = [file('a.txt', 'folder/a.txt'), file('b.txt', 'folder/nested/b.txt')];

  it('retains the selected root for folder upload', () => {
    expect(folderUploadItems(files, false).map((item) => item.relativePath)).toEqual(['folder/a.txt', 'folder/nested/b.txt']);
  });

  it('strips only the selected root for folder contents and keeps nested directories', () => {
    expect(folderUploadItems(files, true).map((item) => item.relativePath)).toEqual(['a.txt', 'nested/b.txt']);
    expect(folderUploadItems([file('a.txt', '')], true)[0].relativePath).toBe('a.txt');
  });
});
