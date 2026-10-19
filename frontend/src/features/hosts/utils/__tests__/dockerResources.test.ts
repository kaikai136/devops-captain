import { describe, expect, it } from 'vitest';
import { dockerField, imageColumns, imageReferences, imageValue, shortDockerId } from '../dockerResources';

describe('Docker resource display', () => {
  const legacy = { id: 'abc', repositories: ['registry:5000/app'], tags: ['v1', 'v2'], size: '10MB', createdAt: '2026-10-19' };
  it('uses legacy fields and hides columns that contain no data', () => {
    expect(imageReferences(legacy)).toEqual(['registry:5000/app:v1', 'registry:5000/app:v2']);
    expect(imageValue(legacy, 'size')).toBe('10MB');
    expect(imageColumns([legacy]).map((column) => column.label)).toEqual(['IMAGE', 'IMAGE ID', 'SIZE', 'CREATED']);
    expect(imageColumns([{ ...legacy, repositories: [], tags: [], size: '', createdAt: '' }]).map((column) => column.key)).toEqual(['id']);
    expect(imageColumns([]).map((column) => column.key)).toEqual(['id']);
  });
  it('shows optional fields only when returned and preserves explicit references', () => {
    const image = { ...legacy, references: ['first:v1', 'second:v2'], diskUsage: '20MB', contentSize: '8MB', extra: 'U' };
    expect(imageReferences(image)).toEqual(['first:v1', 'second:v2']);
    expect(imageValue(image, 'size')).toBe('20MB');
    expect(imageColumns([legacy, image]).map((column) => column.key)).toContain('contentSize');
    expect(imageColumns([image]).map((column) => column.key)).toContain('extra');
    expect(imageReferences({ ...legacy, repositories: ['one', 'two'] })).toEqual(['one', 'two']);
  });
  it('shortens IDs without the sha256 prefix', () => {
    expect(shortDockerId('sha256:1234567890abcdef')).toBe('1234567890ab');
    expect(shortDockerId('abcdef1234567890')).toBe('abcdef123456');
    expect(shortDockerId('short')).toBe('short');
    expect(shortDockerId('')).toBe('—');
  });
  it('shows placeholders without inventing size or extra information', () => {
    for (const value of [null, undefined, '', '   ']) expect(dockerField(value)).toBe('—');
    expect(dockerField('0B')).toBe('0B');
    expect(dockerField('912MB')).toBe('912MB');
    expect(dockerField('U')).toBe('U');
  });
});
