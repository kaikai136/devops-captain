<script setup lang="ts">
import { computed } from 'vue';

import science from '../../../assets/images/login/koi-science.png';

import { useAppContext } from '@app/context';
import AppIcon from '@shared/components/AppIcon.vue';

const { siteIdentity, loginContent, renderSystemTemplate } = useAppContext();

const loginTitle = computed(() => renderSystemTemplate(loginContent.value.title));
const loginDescription = computed(() => renderSystemTemplate(loginContent.value.description));
const loginCopyright = computed(() => renderSystemTemplate(loginContent.value.copyrightTemplate));
</script>

<template>
  <aside class="login-left-panel">
    <div class="login-koi-shape login-koi-shape--one" aria-hidden="true"></div>
    <div class="login-koi-shape login-koi-shape--two" aria-hidden="true"></div>
    <div class="login-koi-shape login-koi-shape--three" aria-hidden="true"></div>
    <div class="login-koi-glass" aria-hidden="true"></div>

    <div class="login-koi-content">
      <div class="login-koi-brand">
        <div class="login-logo-wrap">
          <img :src="siteIdentity.iconUrl" :alt="siteIdentity.appName" />
        </div>
        <strong>{{ siteIdentity.appName }}</strong>
      </div>

      <img class="login-koi-science" :src="science" alt="" aria-hidden="true" />

      <div class="login-koi-copy">
        <p class="login-koi-welcome">欢迎回来</p>
        <h1>{{ loginTitle }}</h1>
        <p>{{ loginDescription }}</p>
      </div>

      <ul class="login-feature-tags" aria-label="平台能力">
        <li><span><AppIcon name="zap" :size="14" /></span>高效管理</li>
        <li><span><AppIcon name="dashboard" :size="14" /></span>现代设计</li>
        <li><span><AppIcon name="shield" :size="14" /></span>安全可靠</li>
      </ul>
    </div>

    <p class="login-copyright">{{ loginCopyright }}</p>
  </aside>
</template>
