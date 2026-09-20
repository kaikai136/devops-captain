import { describe, expect, it } from 'vitest';

import { calculateVirtualWindow, TERMINAL_FILE_ROW_HEIGHT } from '../virtualList';

describe('terminal file virtual list', () => {
  it('renders only the viewport plus overscan for large directories', () => {
    const result = calculateVirtualWindow(10_000, 15_000, 600);

    expect(result.start).toBeGreaterThan(0);
    expect(result.end - result.start).toBeLessThan(50);
    expect(result.totalHeight).toBe(10_000 * TERMINAL_FILE_ROW_HEIGHT);
    expect(result.offset).toBe(result.start * TERMINAL_FILE_ROW_HEIGHT);
  });

  it('keeps the first rows available before the viewport is measured', () => {
    const result = calculateVirtualWindow(1_000, 0, 0);

    expect(result.start).toBe(0);
    expect(result.end).toBeGreaterThan(0);
    expect(result.end).toBeLessThan(40);
  });
});
