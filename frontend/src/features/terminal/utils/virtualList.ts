export const TERMINAL_FILE_ROW_HEIGHT = 30;
export const TERMINAL_FILE_OVERSCAN = 8;
const DEFAULT_VIEWPORT_ROWS = 20;

export interface VirtualWindow {
  start: number;
  end: number;
  offset: number;
  totalHeight: number;
}

export function calculateVirtualWindow(
  itemCount: number,
  scrollTop: number,
  viewportHeight: number,
  rowHeight = TERMINAL_FILE_ROW_HEIGHT,
  overscan = TERMINAL_FILE_OVERSCAN,
): VirtualWindow {
  const safeCount = Math.max(0, itemCount);
  const safeRowHeight = Math.max(1, rowHeight);
  const safeScrollTop = Math.max(0, scrollTop);
  const effectiveViewportHeight = viewportHeight > 0 ? viewportHeight : safeRowHeight * DEFAULT_VIEWPORT_ROWS;
  const firstVisible = Math.floor(safeScrollTop / safeRowHeight);
  const visibleCount = Math.ceil(effectiveViewportHeight / safeRowHeight);
  const start = Math.max(0, firstVisible - Math.max(0, overscan));
  const end = Math.min(safeCount, firstVisible + visibleCount + Math.max(0, overscan));

  return {
    start,
    end,
    offset: start * safeRowHeight,
    totalHeight: safeCount * safeRowHeight,
  };
}
