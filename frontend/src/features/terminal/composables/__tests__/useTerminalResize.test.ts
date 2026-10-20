import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useTerminalResize } from '../useTerminalResize';

interface TestSocket {
  readyState: number;
  send: ReturnType<typeof vi.fn>;
}

interface TestTab {
  id: string;
  kind: 'ssh' | 'rdp';
  mounted: boolean;
  fitAddon: { fit: ReturnType<typeof vi.fn> };
  terminal: { cols: number; rows: number };
  socket: TestSocket | null;
}

class ResizeObserverMock {
  static instances: ResizeObserverMock[] = [];
  readonly observe = vi.fn();
  readonly disconnect = vi.fn();

  constructor(readonly callback: ResizeObserverCallback) {
    ResizeObserverMock.instances.push(this);
  }
}

function createTab(overrides: Partial<TestTab> = {}): TestTab {
  return {
    id: 'tab-1',
    kind: 'ssh',
    mounted: true,
    fitAddon: { fit: vi.fn() },
    terminal: { cols: 120, rows: 40 },
    socket: { readyState: 1, send: vi.fn() },
    ...overrides,
  };
}

describe('useTerminalResize', () => {
  let frames: Map<number, FrameRequestCallback>;
  let nextFrame: number;

  function flushFrame() {
    const callbacks = [...frames.values()];
    frames.clear();
    for (const callback of callbacks) callback(0);
  }

  beforeEach(() => {
    frames = new Map();
    nextFrame = 0;
    vi.stubGlobal('window', {
      requestAnimationFrame: vi.fn((callback: FrameRequestCallback) => {
        frames.set(++nextFrame, callback);
        return nextFrame;
      }),
      cancelAnimationFrame: vi.fn((id: number) => frames.delete(id)),
    });
    ResizeObserverMock.instances = [];
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
    vi.stubGlobal('WebSocket', { OPEN: 1, CLOSED: 3 });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('fits an observed visible SSH terminal and sends the unchanged resize message', () => {
    const tab = createTab();
    const container = {} as HTMLElement;
    const resize = useTerminalResize<TestTab>({
      isVisible: () => true,
      fitRdp: vi.fn(),
    });

    resize.observe(tab, container);

    expect(ResizeObserverMock.instances).toHaveLength(1);
    expect(ResizeObserverMock.instances[0].observe).toHaveBeenCalledWith(container);
    expect(tab.fitAddon.fit).toHaveBeenCalledOnce();
    expect(tab.socket?.send).toHaveBeenCalledWith(JSON.stringify({ type: 'resize', cols: 120, rows: 40 }));

    ResizeObserverMock.instances[0].callback([], ResizeObserverMock.instances[0] as unknown as ResizeObserver);
    expect(tab.fitAddon.fit).toHaveBeenCalledOnce();
    flushFrame();
    expect(tab.fitAddon.fit).toHaveBeenCalledTimes(2);
  });

  it('coalesces observer and page requests per terminal and uses the latest size', () => {
    const tab = createTab();
    const resize = useTerminalResize<TestTab>({ isVisible: () => true, fitRdp: vi.fn() });
    resize.observe(tab, {} as HTMLElement);
    const observer = ResizeObserverMock.instances[0];
    observer.callback([], observer as unknown as ResizeObserver);
    resize.scheduleFit(tab);
    resize.scheduleFit(tab);
    tab.terminal.cols = 140;
    expect(frames.size).toBe(1);
    flushFrame();
    expect(tab.fitAddon.fit).toHaveBeenCalledTimes(2);
    expect(tab.socket?.send).toHaveBeenLastCalledWith(JSON.stringify({ type: 'resize', cols: 140, rows: 40 }));
    resize.scheduleFit(tab);
    flushFrame();
    expect(tab.fitAddon.fit).toHaveBeenCalledTimes(3);
  });

  it('rechecks visibility before fitting and cancels frames on disposal', () => {
    let visible = true;
    const first = createTab();
    const second = createTab({ id: 'tab-2' });
    const resize = useTerminalResize<TestTab>({ isVisible: () => visible, fitRdp: vi.fn() });
    resize.scheduleFit(first);
    visible = false;
    flushFrame();
    expect(first.fitAddon.fit).not.toHaveBeenCalled();
    visible = true;
    resize.scheduleFit(first);
    resize.scheduleFit(second);
    resize.dispose(first.id);
    expect(frames.size).toBe(1);
    resize.disposeAll();
    expect(frames.size).toBe(0);
    flushFrame();
    expect(second.fitAddon.fit).not.toHaveBeenCalled();
  });

  it('lets an immediate fit replace a pending fit', () => {
    const tab = createTab();
    const resize = useTerminalResize<TestTab>({ isVisible: () => true, fitRdp: vi.fn() });
    resize.scheduleFit(tab);
    resize.fit(tab);
    expect(frames.size).toBe(0);
    flushFrame();
    expect(tab.fitAddon.fit).toHaveBeenCalledOnce();
  });

  it('does not fit hidden or unmounted tabs', () => {
    const hidden = createTab();
    const unmounted = createTab({ id: 'tab-2', mounted: false });
    const resize = useTerminalResize<TestTab>({ isVisible: (tab) => tab.id !== hidden.id, fitRdp: vi.fn() });

    resize.fit(hidden);
    resize.fit(unmounted);

    expect(hidden.fitAddon.fit).not.toHaveBeenCalled();
    expect(unmounted.fitAddon.fit).not.toHaveBeenCalled();
  });

  it('delegates RDP fitting and disconnects every observer on dispose', () => {
    const fitRdp = vi.fn();
    const ssh = createTab();
    const rdp = createTab({ id: 'rdp', kind: 'rdp' });
    const resize = useTerminalResize<TestTab>({ isVisible: () => true, fitRdp });

    resize.observe(ssh, {} as HTMLElement);
    resize.observe(rdp, {} as HTMLElement);
    resize.dispose(ssh.id);
    resize.disposeAll();

    expect(fitRdp).toHaveBeenCalledWith(rdp);
    expect(ResizeObserverMock.instances[0].disconnect).toHaveBeenCalledOnce();
    expect(ResizeObserverMock.instances[1].disconnect).toHaveBeenCalledOnce();
  });
});
