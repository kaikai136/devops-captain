import { describe, expect, it } from 'vitest';
import { terminalFileImageMime } from '../fileTypes';

describe('terminal image file types', () => {
  it('recognizes supported image extensions without case sensitivity', () => {
    expect(terminalFileImageMime('logo.PNG')).toBe('image/png');
    expect(terminalFileImageMime('preview.svg')).toBe('image/svg+xml');
    expect(terminalFileImageMime('photo.webp')).toBe('image/webp');
  });

  it('leaves other files for UTF-8 detection or download', () => {
    expect(terminalFileImageMime('app.py')).toBe('application/octet-stream');
    expect(terminalFileImageMime('archive.zip')).toBe('application/octet-stream');
  });
});
