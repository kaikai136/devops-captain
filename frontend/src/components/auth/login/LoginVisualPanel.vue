<script setup lang="ts">
import LoginCharacters from './LoginCharacters.vue';
import type { LoginCharacterProps } from '../../../composables/auth/useLoginCharacters';

defineProps<LoginCharacterProps>();
</script>

<template>
  <aside class="login-left-panel">
    <div class="login-koi-shape login-koi-shape--one" aria-hidden="true"></div>
    <div class="login-koi-shape login-koi-shape--two" aria-hidden="true"></div>
    <div class="login-koi-shape login-koi-shape--three" aria-hidden="true"></div>
    <div class="login-koi-glass" aria-hidden="true"></div>

    <LoginCharacters :active="active" :is-typing="isTyping" :show-password="showPassword" :password-length="passwordLength" />
  </aside>
</template>
