import { computed, onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue';
import type { Point } from '../../components/auth/login/characterPoses';

export interface LoginCharacterProps {
  active: boolean;
  isTyping: boolean;
  showPassword: boolean;
  passwordLength: number;
}

export function useLoginCharacters(props: LoginCharacterProps, viewport: Ref<HTMLElement | null>, stage: Ref<HTMLElement | null>) {
  const scale = ref(0);
  const inViewport = ref(false);
  const pageVisible = ref(false);
  const reducedMotion = ref(false);
  const pointer = ref<Point | null>(null);
  const purpleBlink = ref(false);
  const blackBlink = ref(false);
  const glance = ref(false);
  const peek = ref(false);
  const running = computed(() => props.active && inViewport.value && pageVisible.value && scale.value > 0 && !reducedMotion.value);
  const lookAway = computed(() => props.passwordLength > 0 && props.showPassword);
  let resizeObserver: ResizeObserver | undefined;
  let intersectionObserver: IntersectionObserver | undefined;
  let motionQuery: MediaQueryList | undefined;

  function measure() {
    const bounds = viewport.value?.getBoundingClientRect();
    scale.value = bounds ? Math.max(0, Math.min(bounds.width / 550, bounds.height / 500, 1)) : 0;
  }
  function syncVisibility() { pageVisible.value = document.visibilityState === 'visible'; }
  function syncMotion() { reducedMotion.value = motionQuery?.matches ?? false; }

  onMounted(() => {
    motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    syncMotion();
    syncVisibility();
    motionQuery.addEventListener('change', syncMotion);
    document.addEventListener('visibilitychange', syncVisibility);
    resizeObserver = new ResizeObserver(measure);
    intersectionObserver = new IntersectionObserver(([entry]) => { inViewport.value = entry?.isIntersecting ?? false; });
    if (viewport.value) {
      resizeObserver.observe(viewport.value);
      intersectionObserver.observe(viewport.value);
    }
    measure();
  });

  watch([running, () => props.isTyping, lookAway], ([enabled, typing, away], _, onCleanup) => {
    purpleBlink.value = false;
    blackBlink.value = false;
    glance.value = false;
    peek.value = false;
    if (!enabled) { pointer.value = null; return; }

    const timers = new Set<ReturnType<typeof setTimeout>>();
    let frame: number | undefined;
    let pendingPointer: Point | null = null;
    function later(callback: () => void, delay: number) {
      const timer = setTimeout(() => { timers.delete(timer); callback(); }, delay);
      timers.add(timer);
    }
    function blink(eye: Ref<boolean>) {
      later(() => {
        eye.value = true;
        later(() => { eye.value = false; blink(eye); }, 150);
      }, 3000 + Math.random() * 4000);
    }
    function schedulePeek() {
      later(() => {
        peek.value = true;
        later(() => { peek.value = false; schedulePeek(); }, 800);
      }, 2000 + Math.random() * 3000);
    }
    function move(event: PointerEvent) {
      if (event.pointerType === 'touch') return;
      pendingPointer = { x: event.clientX, y: event.clientY };
      if (frame !== undefined) return;
      frame = window.requestAnimationFrame(() => {
        frame = undefined;
        const bounds = stage.value?.getBoundingClientRect();
        if (bounds && pendingPointer && scale.value > 0) {
          pointer.value = { x: (pendingPointer.x - bounds.left) / scale.value, y: (pendingPointer.y - bounds.top) / scale.value };
        }
      });
    }
    function resetPointer() {
      if (frame !== undefined) window.cancelAnimationFrame(frame);
      frame = undefined;
      pendingPointer = null;
      pointer.value = null;
    }

    blink(purpleBlink);
    blink(blackBlink);
    if (typing) { glance.value = true; later(() => { glance.value = false; }, 800); }
    if (away) schedulePeek();
    window.addEventListener('pointermove', move, { passive: true });
    window.addEventListener('blur', resetPointer);
    document.addEventListener('pointerleave', resetPointer);
    onCleanup(() => {
      timers.forEach(clearTimeout);
      if (frame !== undefined) window.cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('blur', resetPointer);
      document.removeEventListener('pointerleave', resetPointer);
    });
  }, { immediate: true });

  onBeforeUnmount(() => {
    resizeObserver?.disconnect();
    intersectionObserver?.disconnect();
    motionQuery?.removeEventListener('change', syncMotion);
    document.removeEventListener('visibilitychange', syncVisibility);
  });

  const interaction = computed(() => ({
    pointer: pointer.value,
    isTyping: running.value && props.isTyping,
    maskedPassword: running.value && props.passwordLength > 0 && !props.showPassword,
    lookAway: running.value && lookAway.value,
    glance: glance.value,
    peek: peek.value,
  }));

  return { scale, running, interaction, purpleBlink, blackBlink };
}
