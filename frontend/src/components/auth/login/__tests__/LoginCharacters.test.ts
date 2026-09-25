import { createRenderer, h, nextTick, reactive, ref, shallowRef } from 'vue';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useLoginCharacterFormState } from '../../../../composables/auth/useLoginCharacterFormState';
import { useLoginCharacters, type LoginCharacterProps } from '../../../../composables/auth/useLoginCharacters';
import { characterPose, characters, pupilOffset, type CharacterInteraction } from '../characterPoses';

const renderer = createRenderer<object, object>({
  createElement: () => ({}), createText: () => ({}), createComment: () => ({}),
  insert: () => {}, remove: () => {}, setText: () => {}, setElementText: () => {}, patchProp: () => {},
  parentNode: () => null, nextSibling: () => null,
});
const unmounts: Array<() => void> = [];
function mount<T>(setup: () => T) {
  let state!: T;
  const app = renderer.createApp({ setup() { state = setup(); return () => h('div'); } });
  app.mount({});
  const unmount = () => { app.unmount(); unmounts.splice(unmounts.indexOf(unmount), 1); };
  unmounts.push(unmount);
  return { state, unmount };
}

class Input extends EventTarget {
  value = '';
  type = 'password';
}
class Observer {
  static instances: Observer[] = [];
  observe = vi.fn();
  disconnect = vi.fn();
  constructor(public callback: (entries: Array<{ isIntersecting: boolean }>) => void) { Observer.instances.push(this); }
}
let doc: EventTarget & { activeElement: Input | null; visibilityState: string };
let motion: EventTarget & { matches: boolean };
let win: EventTarget & { requestAnimationFrame: ReturnType<typeof vi.fn>; cancelAnimationFrame: ReturnType<typeof vi.fn> };
let frames: Map<number, FrameRequestCallback>;

beforeEach(() => {
  vi.useFakeTimers();
  vi.spyOn(Math, 'random').mockReturnValue(0.5);
  Observer.instances = [];
  frames = new Map();
  let frameId = 0;
  doc = Object.assign(new EventTarget(), { activeElement: null, visibilityState: 'visible' });
  motion = Object.assign(new EventTarget(), { matches: false });
  win = Object.assign(new EventTarget(), {
    matchMedia: () => motion,
    requestAnimationFrame: vi.fn((callback: FrameRequestCallback) => { frames.set(++frameId, callback); return frameId; }),
    cancelAnimationFrame: vi.fn((id: number) => frames.delete(id)),
  });
  vi.stubGlobal('window', win);
  vi.stubGlobal('document', doc);
  vi.stubGlobal('ResizeObserver', Observer);
  vi.stubGlobal('IntersectionObserver', Observer);
  vi.stubGlobal('MutationObserver', Observer);
});
afterEach(() => {
  [...unmounts].forEach((unmount) => unmount());
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const neutral: CharacterInteraction = { pointer: null, isTyping: false, maskedPassword: false, lookAway: false, glance: false, peek: false };

describe('character poses', () => {
  it('keeps neutral eyes centred and bounds cursor tracking and body tilt', () => {
    expect(pupilOffset(null, { x: 0, y: 0 }, 5)).toEqual({ x: 0, y: 0 });
    for (const character of characters) {
      const pose = characterPose(character.key, { ...neutral, pointer: { x: 10000, y: -10000 } });
      expect(Math.abs(pose.skew)).toBeLessThanOrEqual(6);
      for (const pupil of pose.pupils) expect(Math.hypot(pupil.x, pupil.y)).toBeCloseTo(character.travel);
    }
  });

  it('leans for account focus or a masked password and looks away for a visible password', () => {
    for (const state of [{ isTyping: true }, { maskedPassword: true }]) {
      expect(characterPose('purple', { ...neutral, ...state })).toMatchObject({ height: 440, skew: -12, translate: 40 });
    }
    for (const character of characters) {
      const pose = characterPose(character.key, { ...neutral, isTyping: true, glance: true, lookAway: true });
      expect(pose).toMatchObject({ skew: 0, translate: 0 });
      expect(pose.pupils[0].x).toBeLessThan(0);
    }
    expect(characterPose('purple', { ...neutral, lookAway: true, peek: true }).pupils[0]).toEqual({ x: 4, y: 5 });
    expect(characterPose('black', { ...neutral, lookAway: true, peek: true }).pupils[0].x).toBeLessThan(0);
  });
});

function mountForm() {
  const username = shallowRef<Input | null>(new Input());
  const password = shallowRef<Input | null>(new Input());
  const modelLength = ref(0);
  const mounted = mount(() => useLoginCharacterFormState({
    getUsernameInput: () => username.value as HTMLInputElement | null,
    getPasswordInput: () => password.value as HTMLInputElement | null,
    getPasswordLength: () => modelLength.value,
  }));
  return { ...mounted, username, password, modelLength };
}

describe('existing login input linkage', () => {
  it('tracks focus, autofill/change, input clearing and native password visibility', async () => {
    const { state, username, password } = mountForm();
    await nextTick();
    username.value!.dispatchEvent(new Event('focus'));
    expect(state.isTyping.value).toBe(true);
    username.value!.dispatchEvent(new Event('blur'));
    expect(state.isTyping.value).toBe(false);
    password.value!.value = 'autofill';
    password.value!.dispatchEvent(new Event('change'));
    expect(state.passwordLength.value).toBe(8);
    password.value!.type = 'text';
    Observer.instances[0].callback([]);
    expect(state.showPassword.value).toBe(true);
    password.value!.value = '';
    password.value!.dispatchEvent(new Event('input'));
    expect(state.passwordLength.value).toBe(0);
    expect(Object.keys(state).sort()).toEqual(['isTyping', 'passwordLength', 'showPassword']);
  });

  it('reads initial/model-updated values and resets/rebinds when switching authentication steps', async () => {
    const { state, username, password, modelLength } = mountForm();
    await nextTick();
    password.value!.value = 'model update';
    modelLength.value = 12;
    await nextTick();
    expect(state.passwordLength.value).toBe(12);
    const previousUsername = username.value!;
    const previousPassword = password.value!;
    username.value = null;
    password.value = null;
    await nextTick();
    expect(state.isTyping.value).toBe(false);
    expect(state.passwordLength.value).toBe(0);
    expect(state.showPassword.value).toBe(false);
    previousUsername.dispatchEvent(new Event('focus'));
    previousPassword.dispatchEvent(new Event('input'));
    expect(state.isTyping.value).toBe(false);
    expect(state.passwordLength.value).toBe(0);
    username.value = new Input();
    password.value = new Input();
    password.value.value = 'restored';
    doc.activeElement = username.value;
    await nextTick();
    expect(state.isTyping.value).toBe(true);
    expect(state.passwordLength.value).toBe(8);
    expect(Observer.instances.slice(0, -1).every(observer => observer.disconnect.mock.calls.length === 1)).toBe(true);
  });

  it('removes input listeners and type observation on unmount', async () => {
    const { state, username, password, unmount } = mountForm();
    await nextTick();
    unmount();
    expect(Observer.instances[0].disconnect).toHaveBeenCalledOnce();
    username.value!.dispatchEvent(new Event('focus'));
    password.value!.value = 'late event';
    password.value!.dispatchEvent(new Event('input'));
    expect(state.isTyping.value).toBe(false);
    expect(state.passwordLength.value).toBe(0);
  });
});

async function mountAnimation(active = true) {
  const props = reactive<LoginCharacterProps>({ active, isTyping: false, showPassword: false, passwordLength: 0 });
  const bounds = { width: 550, height: 500, left: 10, top: 20 };
  const element = { getBoundingClientRect: () => bounds } as HTMLElement;
  const mounted = mount(() => useLoginCharacters(props, shallowRef(element), shallowRef(element)));
  Observer.instances[1].callback([{ isIntersecting: true }]);
  await nextTick();
  const move = () => win.dispatchEvent(Object.assign(new Event('pointermove'), { pointerType: 'mouse', clientX: 100, clientY: 120 }));
  return { ...mounted, props, bounds, move };
}

describe('character animation lifecycle', () => {
  it('blinks for 150ms and repeats within the 3–7 second interval', async () => {
    const { state } = await mountAnimation();
    vi.advanceTimersByTime(4999);
    expect(state.purpleBlink.value).toBe(false);
    vi.advanceTimersByTime(1);
    expect(state.purpleBlink.value).toBe(true);
    expect(state.blackBlink.value).toBe(true);
    vi.advanceTimersByTime(150);
    expect(state.purpleBlink.value).toBe(false);
    vi.advanceTimersByTime(5000);
    expect(state.purpleBlink.value).toBe(true);
  });

  it('glances for 800ms and peeks only while a nonempty password is visible', async () => {
    const { state, props } = await mountAnimation();
    props.isTyping = true;
    await nextTick();
    expect(state.interaction.value.glance).toBe(true);
    vi.advanceTimersByTime(800);
    expect(state.interaction.value.glance).toBe(false);
    props.passwordLength = 8;
    props.showPassword = true;
    await nextTick();
    vi.advanceTimersByTime(3499);
    expect(state.interaction.value.peek).toBe(false);
    vi.advanceTimersByTime(1);
    expect(state.interaction.value.peek).toBe(true);
    vi.advanceTimersByTime(800);
    expect(state.interaction.value.peek).toBe(false);
    props.passwordLength = 0;
    await nextTick();
    vi.advanceTimersByTime(4000);
    expect(state.interaction.value.lookAway).toBe(false);
    expect(state.interaction.value.peek).toBe(false);
  });

  it('coalesces pointer updates into one frame and uses logical coordinates after scaling', async () => {
    const { state, bounds, move } = await mountAnimation();
    bounds.width = 275;
    bounds.height = 250;
    Observer.instances[0].callback([]);
    move(); move();
    expect(frames.size).toBe(1);
    const [id, callback] = [...frames][0];
    frames.delete(id);
    callback(0);
    expect(state.interaction.value.pointer).toEqual({ x: 180, y: 200 });
    win.dispatchEvent(new Event('blur'));
    expect(state.interaction.value.pointer).toBeNull();
  });

  it('waits for the welcome overlay, pauses offscreen/in background, and resumes without duplicate timers', async () => {
    const { state, props, move } = await mountAnimation(false);
    expect(vi.getTimerCount()).toBe(0);
    props.active = true;
    await nextTick();
    expect(vi.getTimerCount()).toBe(2);
    for (const pause of ['overlay', 'offscreen', 'background']) {
      move();
      if (pause === 'overlay') props.active = false;
      if (pause === 'offscreen') Observer.instances[1].callback([{ isIntersecting: false }]);
      if (pause === 'background') { doc.visibilityState = 'hidden'; doc.dispatchEvent(new Event('visibilitychange')); }
      await nextTick();
      expect(state.running.value).toBe(false);
      expect(state.interaction.value.pointer).toBeNull();
      expect(vi.getTimerCount()).toBe(0);
      expect(frames.size).toBe(0);
      move();
      expect(frames.size).toBe(0);
      props.active = true;
      Observer.instances[1].callback([{ isIntersecting: true }]);
      doc.visibilityState = 'visible'; doc.dispatchEvent(new Event('visibilitychange'));
      await nextTick();
      expect(vi.getTimerCount()).toBe(2);
    }
  });

  it('uses static poses with reduced motion and stops at zero size on mobile', async () => {
    const { state, props, bounds, move } = await mountAnimation();
    props.isTyping = true;
    props.passwordLength = 4;
    props.showPassword = true;
    motion.matches = true;
    motion.dispatchEvent(new Event('change'));
    await nextTick();
    move();
    expect(state.interaction.value).toEqual(neutral);
    expect(vi.getTimerCount()).toBe(0);
    expect(frames.size).toBe(0);
    motion.matches = false;
    motion.dispatchEvent(new Event('change'));
    bounds.width = 0;
    Observer.instances[0].callback([]);
    await nextTick();
    expect(state.running.value).toBe(false);
    expect(state.scale.value).toBe(0);
  });

  it('disconnects observers, timers, frames and global listeners on unmount', async () => {
    const removeWindow = vi.spyOn(win, 'removeEventListener');
    const removeDocument = vi.spyOn(doc, 'removeEventListener');
    const removeMotion = vi.spyOn(motion, 'removeEventListener');
    const { props, move, unmount } = await mountAnimation();
    props.showPassword = true; props.passwordLength = 5;
    await nextTick();
    move();
    expect(frames.size).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
    expect(frames.size).toBe(0);
    expect(Observer.instances.every(observer => observer.disconnect.mock.calls.length === 1)).toBe(true);
    expect(removeWindow.mock.calls.map(call => call[0])).toEqual(expect.arrayContaining(['pointermove', 'blur']));
    expect(removeDocument.mock.calls.map(call => call[0])).toEqual(expect.arrayContaining(['visibilitychange', 'pointerleave']));
    expect(removeMotion.mock.calls.map(call => call[0])).toContain('change');
    move();
    expect(frames.size).toBe(0);
  });
});
