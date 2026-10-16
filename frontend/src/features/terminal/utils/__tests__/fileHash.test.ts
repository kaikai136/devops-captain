import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { terminalFileHash } from '../fileHash';

describe('terminalFileHash', () => {
  it.each(['', 'abc', '\ufeff中文\r\n', 'same', 'size', 'a'.repeat(55), 'a'.repeat(56), 'a'.repeat(64), 'a'.repeat(1000000)])(
    'matches SHA-256 for UTF-8 and block boundaries (case %#)', content => {
      const bytes = new TextEncoder().encode(content);
      expect(terminalFileHash(bytes)).toBe(createHash('sha256').update(bytes).digest('hex'));
    },
  );
});
