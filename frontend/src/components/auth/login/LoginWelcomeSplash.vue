<script setup lang="ts">
defineProps<{ exiting: boolean }>();
</script>

<template>
  <div
    class="login-welcome-splash"
    :class="{ 'is-exiting': exiting }"
    role="status"
    aria-label="欢迎回来"
  >
    <div class="login-welcome-text" aria-hidden="true">
      <span v-for="character in '欢迎回来'" :key="character" class="login-welcome-wave">{{ character }}</span>
    </div>
  </div>
</template>

<style scoped>
.login-welcome-splash {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  background:
    radial-gradient(1200px 800px at 20% -10%, rgba(255, 255, 255, 0.28), transparent 60%),
    linear-gradient(120deg, #a5b4fc 0%, #93c5fd 33%, #a5f3fc 66%, #fbcfe8 100%);
  user-select: none;
  pointer-events: auto;
  transition: opacity 0.4s ease-out;
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.login-welcome-splash.is-exiting {
  opacity: 0;
}

.login-welcome-text {
  display: flex;
  font-size: clamp(56px, 10vw, 108px);
  font-weight: 800;
  letter-spacing: 0.08em;
  color: #fff;
  text-shadow: 0 4px 24px rgba(37, 42, 99, 0.5);
  animation: login-welcome-fade-in 0.5s ease-out 0.12s forwards;
  opacity: 0;
}

.login-welcome-wave {
  display: inline-block;
  animation: login-welcome-wave 2.6s ease-in-out infinite;
}

.login-welcome-wave:nth-child(2) {
  animation-delay: 0.12s;
}

.login-welcome-wave:nth-child(3) {
  animation-delay: 0.24s;
}

.login-welcome-wave:nth-child(4) {
  animation-delay: 0.36s;
}

@keyframes login-welcome-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

@keyframes login-welcome-wave {
  0%, 100% { transform: translateY(0); }
  25% { transform: translateY(-11px); }
  50% { transform: translateY(6px); }
  75% { transform: translateY(-6px); }
}

@media (prefers-reduced-motion: reduce) {
  .login-welcome-splash {
    transition: none;
  }

  .login-welcome-text,
  .login-welcome-wave {
    animation: none;
    opacity: 1;
  }
}
</style>
