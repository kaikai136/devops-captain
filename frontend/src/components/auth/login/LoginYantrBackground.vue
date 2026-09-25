<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';

const props = withDefaults(
  defineProps<{
    dark?: boolean;
  }>(),
  { dark: false },
);

type Particle = {
  x: number;
  y: number;
  size: number;
  vx: number;
  vy: number;
};

const canvas = ref<HTMLCanvasElement | null>(null);
let context: CanvasRenderingContext2D | null = null;
let particles: Particle[] = [];
let animationFrame: number | null = null;
let resizeHandler: (() => void) | null = null;
let mouseMoveHandler: ((event: MouseEvent) => void) | null = null;
let mouseLeaveHandler: (() => void) | null = null;
let visibilityHandler: (() => void) | null = null;
let motionQuery: MediaQueryList | null = null;
let motionChangeHandler: (() => void) | null = null;
let width = 0;
let height = 0;
let pixelRatio = 1;
let reducedMotion = false;
let pageVisible = true;
let mouse = { x: -500, y: -500, targetX: -500, targetY: -500, active: false };

function readAccentRgb() {
  const value = getComputedStyle(canvas.value as Element).getPropertyValue('--login-accent-rgb').trim();
  return value || (props.dark ? '129, 140, 248' : '99, 102, 241');
}

function resizeCanvas() {
  const element = canvas.value;
  if (!element || !context) return;
  width = window.innerWidth;
  height = window.innerHeight;
  pixelRatio = Math.min(window.devicePixelRatio || 1, 2);
  element.width = Math.max(1, Math.floor(width * pixelRatio));
  element.height = Math.max(1, Math.floor(height * pixelRatio));
  element.style.width = `${width}px`;
  element.style.height = `${height}px`;
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  createParticles();
  drawFrame();
}

function createParticles() {
  const lowPower = width < 700 || (navigator.hardwareConcurrency || 4) <= 2;
  const areaCount = Math.floor((width * height) / (lowPower ? 26000 : 15000));
  const count = Math.min(lowPower ? 42 : 100, Math.max(lowPower ? 18 : 28, areaCount));
  particles = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    size: lowPower ? 1.2 + Math.random() * 1.8 : 1.5 + Math.random() * 2.5,
    vx: (Math.random() - 0.5) * (lowPower ? 0.25 : 0.4),
    vy: (Math.random() - 0.5) * (lowPower ? 0.25 : 0.4),
  }));
}

function drawFrame() {
  const element = canvas.value;
  const ctx = context;
  if (!element || !ctx) return;
  const accent = readAccentRgb();
  const dark = props.dark;
  const base = dark ? '#0a0f1a' : '#f8fafc';
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, width, height);

  if (mouse.active && !reducedMotion) {
    const radius = width < 700 ? 260 : 450;
    const gradient = ctx.createRadialGradient(mouse.targetX, mouse.targetY, 0, mouse.targetX, mouse.targetY, radius);
    gradient.addColorStop(0, `rgba(${accent}, ${dark ? 0.16 : 0.1})`);
    gradient.addColorStop(0.42, `rgba(${accent}, ${dark ? 0.07 : 0.04})`);
    gradient.addColorStop(1, `rgba(${accent}, 0)`);
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(mouse.targetX, mouse.targetY, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  const influenceRadius = width < 700 ? 92 : 140;
  const shouldDrawLines = !reducedMotion && width >= 700;
  const mx = mouse.targetX;
  const my = mouse.targetY;
  particles.forEach((particle) => {
    if (!reducedMotion) {
      particle.x += particle.vx;
      particle.y += particle.vy;
      if (particle.x < 0 || particle.x > width) particle.vx *= -1;
      if (particle.y < 0 || particle.y > height) particle.vy *= -1;
    }

    if (mouse.active && !reducedMotion) {
      const dx = mx - particle.x;
      const dy = my - particle.y;
      const distance = Math.sqrt(dx * dx + dy * dy) || 1;
      if (distance < influenceRadius) {
        const force = (influenceRadius - distance) / influenceRadius;
        particle.x -= (dx / distance) * force * 1.5;
        particle.y -= (dy / distance) * force * 1.5;
        if (shouldDrawLines) {
          ctx.strokeStyle = `rgba(${accent}, ${0.25 * force})`;
          ctx.lineWidth = 0.8;
          ctx.beginPath();
          ctx.moveTo(particle.x, particle.y);
          ctx.lineTo(mx, my);
          ctx.stroke();
        }
      }
    }

    ctx.fillStyle = `rgba(${accent}, ${dark ? 0.28 : 0.22})`;
    ctx.beginPath();
    ctx.arc(particle.x, particle.y, particle.size, 0, Math.PI * 2);
    ctx.fill();
  });

  if (mouse.active && !reducedMotion) {
    ctx.lineWidth = 1.5;
    ctx.strokeStyle = `rgba(${accent}, ${dark ? 0.52 : 0.35})`;
    ctx.beginPath();
    ctx.arc(mouse.targetX, mouse.targetY, width < 700 ? 14 : 18, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = `rgba(${accent}, ${dark ? 0.8 : 0.6})`;
    ctx.beginPath();
    ctx.arc(mouse.targetX, mouse.targetY, 3, 0, Math.PI * 2);
    ctx.fill();
  }
}

function animate() {
  animationFrame = null;
  if (!pageVisible || reducedMotion) return;
  if (mouse.active) {
    mouse.targetX += (mouse.x - mouse.targetX) * 0.1;
    mouse.targetY += (mouse.y - mouse.targetY) * 0.1;
  }
  drawFrame();
  animationFrame = window.requestAnimationFrame(animate);
}

function startAnimation() {
  if (animationFrame === null && pageVisible && !reducedMotion) animationFrame = window.requestAnimationFrame(animate);
}

function stopAnimation() {
  if (animationFrame !== null) {
    window.cancelAnimationFrame(animationFrame);
    animationFrame = null;
  }
}

function syncMotionPreference() {
  reducedMotion = Boolean(motionQuery?.matches);
  stopAnimation();
  drawFrame();
  startAnimation();
}

watch(
  () => props.dark,
  () => drawFrame(),
  { flush: 'post' },
);

onMounted(() => {
  const element = canvas.value;
  if (!element) return;
  context = element.getContext('2d', { alpha: true });
  if (!context) return;

  motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  reducedMotion = motionQuery.matches;
  pageVisible = document.visibilityState === 'visible';
  resizeHandler = resizeCanvas;
  mouseMoveHandler = (event) => {
    mouse.x = event.clientX;
    mouse.y = event.clientY;
    if (!mouse.active) {
      mouse.targetX = event.clientX;
      mouse.targetY = event.clientY;
    }
    mouse.active = true;
  };
  mouseLeaveHandler = () => {
    mouse.active = false;
  };
  visibilityHandler = () => {
    pageVisible = document.visibilityState === 'visible';
    if (pageVisible) startAnimation();
    else stopAnimation();
  };
  motionChangeHandler = syncMotionPreference;

  resizeCanvas();
  window.addEventListener('resize', resizeHandler);
  window.addEventListener('mousemove', mouseMoveHandler);
  window.addEventListener('mouseleave', mouseLeaveHandler);
  document.addEventListener('visibilitychange', visibilityHandler);
  motionQuery.addEventListener?.('change', motionChangeHandler);
  startAnimation();
});

onUnmounted(() => {
  stopAnimation();
  if (resizeHandler) window.removeEventListener('resize', resizeHandler);
  if (mouseMoveHandler) window.removeEventListener('mousemove', mouseMoveHandler);
  if (mouseLeaveHandler) window.removeEventListener('mouseleave', mouseLeaveHandler);
  if (visibilityHandler) document.removeEventListener('visibilitychange', visibilityHandler);
  if (motionQuery && motionChangeHandler) motionQuery.removeEventListener?.('change', motionChangeHandler);
  context = null;
  particles = [];
});
</script>

<template>
  <canvas ref="canvas" class="login-yantr-background" aria-hidden="true" />
</template>
