import { afterEach, describe, expect, it, vi } from 'vitest';
import { useShellState } from '../../composables/app/useShellState';

afterEach(() => vi.unstubAllGlobals());

function environment(reduced = false) {
  const setItem = vi.fn();
  vi.stubGlobal('window', { innerWidth: 1000, innerHeight: 800, matchMedia: () => ({ matches: reduced }), localStorage: { getItem: () => null, setItem } });
  return setItem;
}

describe('theme ripple', () => {
  it('switches and persists immediately without view transitions', async () => {
    const persist = environment();
    vi.stubGlobal('document', {});
    const shell = useShellState();
    await shell.toggleWorkspaceTheme();
    expect(shell.isWorkspaceDark.value).toBe(true);
    expect(persist).toHaveBeenCalledWith('ops-tool.workspace-theme', 'dark');
  });

  it('reveals the new snapshot from the click and cleans up', async () => {
    environment();
    const add = vi.fn();
    const remove = vi.fn();
    const animate = vi.fn((_frames: { clipPath: string[] }, _options: { pseudoElement: string }) => ({ finished: Promise.resolve() }));
    const startViewTransition = vi.fn((update: () => Promise<void>) => ({ ready: update(), finished: Promise.resolve() }));
    vi.stubGlobal('document', { startViewTransition, documentElement: { animate, classList: { add, remove } } });
    const shell = useShellState();
    const changing = shell.toggleWorkspaceTheme({ clientX: 900, clientY: 40, detail: 1 } as MouseEvent);
    await shell.toggleWorkspaceTheme();
    await changing;
    expect(startViewTransition).toHaveBeenCalledTimes(1);
    expect(animate.mock.calls[0][0].clipPath[0]).toBe('circle(0px at 900px 40px)');
    expect(animate.mock.calls[0][1].pseudoElement).toBe('::view-transition-new(root)');
    expect(shell.isWorkspaceDark.value).toBe(true);
    expect(remove).toHaveBeenCalledWith('workspace-theme-transition');
  });

  it('honors reduced motion', async () => {
    environment(true);
    const startViewTransition = vi.fn();
    vi.stubGlobal('document', { startViewTransition });
    const shell = useShellState();
    await shell.toggleWorkspaceTheme();
    expect(startViewTransition).not.toHaveBeenCalled();
    expect(shell.isWorkspaceDark.value).toBe(true);
  });
});
