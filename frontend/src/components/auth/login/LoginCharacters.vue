<script setup lang="ts">
import { computed, ref } from 'vue';
import { useLoginCharacters, type LoginCharacterProps } from '../../../composables/auth/useLoginCharacters';
import { characterPose, characters } from './characterPoses';

const props = defineProps<LoginCharacterProps>();
const viewport = ref<HTMLElement | null>(null);
const stage = ref<HTMLElement | null>(null);
const { scale, running, interaction, purpleBlink, blackBlink } = useLoginCharacters(props, viewport, stage);
const figures = computed(() => characters.map((character) => ({
  ...character,
  pose: characterPose(character.key, interaction.value),
  blinking: character.key === 'purple' ? purpleBlink.value : character.key === 'black' && blackBlink.value,
})));
</script>

<template>
  <div ref="viewport" class="login-character-viewport" aria-hidden="true">
    <div
      ref="stage"
      class="login-character-stage"
      :class="{ 'is-paused': !running }"
      :style="{ transform: `translate(-50%, -50%) scale(${scale})` }"
    >
      <div
        v-for="figure in figures"
        :key="figure.key"
        class="login-character"
        :class="`login-character--${figure.key}`"
        :style="{
          left: `${figure.left}px`, width: `${figure.width}px`, height: `${figure.pose.height}px`,
          transform: `skewX(${figure.pose.skew}deg) translateX(${figure.pose.translate}px)`,
        }"
      >
        <div class="character-face" :style="{ left: `${figure.pose.faceX}px`, top: `${figure.pose.faceY}px`, gap: `${figure.gap}px` }">
          <div
            v-for="(pupil, index) in figure.pose.pupils"
            :key="index"
            class="character-eye"
            :class="{ 'is-blinking': figure.blinking, 'has-white': figure.key === 'purple' || figure.key === 'black' }"
            :style="{ width: `${figure.eye}px`, height: `${figure.eye}px` }"
          >
            <div class="character-pupil" :style="{ width: `${figure.pupil}px`, height: `${figure.pupil}px`, transform: `translate(${pupil.x}px, ${pupil.y}px)` }"></div>
          </div>
        </div>
        <div v-if="figure.key === 'yellow'" class="character-mouth" :style="{ left: `${figure.pose.mouthX}px`, top: `${figure.pose.mouthY}px` }"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-character-viewport {
  position: absolute;
  inset: 24px;
  z-index: 2;
  overflow: hidden;
  pointer-events: none;
  user-select: none;
}

.login-character-stage {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 550px;
  height: 500px;
  transform-origin: center;
}

.login-character {
  position: absolute;
  bottom: 40px;
  transform-origin: bottom center;
  transition: transform 700ms ease-in-out, height 700ms ease-in-out;
}

.login-character--purple { z-index: 1; background: #6c3ff5; border-radius: 10px 10px 0 0; }
.login-character--black { z-index: 2; background: #2d2d2d; border-radius: 8px 8px 0 0; }
.login-character--orange { z-index: 3; background: #ff9b6b; border-radius: 120px 120px 0 0; }
.login-character--yellow { z-index: 4; background: #e8d754; border-radius: 70px 70px 0 0; }

.character-face {
  position: absolute;
  display: flex;
  transition: left 700ms ease-in-out, top 700ms ease-in-out;
}

.login-character--orange .character-face,
.login-character--yellow .character-face {
  transition: left 200ms ease-out, top 200ms ease-out;
}

.character-eye {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: transform 150ms ease-out;
}

.character-eye.has-white { background: #fff; overflow: hidden; }
.character-eye.is-blinking { transform: scaleY(0.12); }
.character-eye.is-blinking .character-pupil { opacity: 0; }
.character-pupil { flex-shrink: 0; border-radius: 50%; background: #2d2d2d; transition: transform 100ms ease-out; }
.character-mouth { position: absolute; width: 80px; height: 4px; border-radius: 999px; background: #2d2d2d; transition: left 200ms ease-out, top 200ms ease-out; }
.is-paused * { transition: none; }

@media (prefers-reduced-motion: reduce) {
  .login-character-stage * { transition: none; }
}
</style>
