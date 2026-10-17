<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import type { EChartsCoreOption, EChartsType } from 'echarts/core';
import { init, use } from 'echarts/core';
import { BarChart, GaugeChart, LineChart, PieChart } from 'echarts/charts';
import { GraphicComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

import { useAppContext } from '@app/context';

use([BarChart, GaugeChart, LineChart, PieChart, GraphicComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer]);

const props = withDefaults(
  defineProps<{
    option: Record<string, unknown>;
    ariaLabel?: string;
    renderer?: 'canvas' | 'svg';
  }>(),
  {
    ariaLabel: '仪表盘图表',
    renderer: 'canvas',
  },
);

const { isWorkspaceDark } = useAppContext();

const chartElement = ref<HTMLDivElement | null>(null);
const chart = shallowRef<EChartsType | null>(null);

let resizeObserver: ResizeObserver | null = null;
let resizeFrame = 0;
let mounted = false;

onMounted(() => {
  mounted = true;
  initChart();
  bindResize();
});

watch(
  () => props.option,
  (option) => {
    setOption(option);
  },
);

watch(isWorkspaceDark, async () => {
  if (!mounted) return;
  disposeChart();
  await nextTick();
  initChart();
});

onBeforeUnmount(() => {
  mounted = false;
  unbindResize();
  disposeChart();
});

function initChart() {
  if (!chartElement.value) return;
  chart.value = init(chartElement.value, isWorkspaceDark.value ? 'dark' : null, {
    renderer: props.renderer,
    devicePixelRatio: window.devicePixelRatio || 1,
  });
  setOption(props.option);
}

function setOption(option: Record<string, unknown>) {
  if (!chart.value) return;
  chart.value.setOption(option as EChartsCoreOption, {
    notMerge: true,
    lazyUpdate: true,
  });
}

function bindResize() {
  if (typeof ResizeObserver !== 'undefined' && chartElement.value) {
    resizeObserver = new ResizeObserver(resizeChart);
    resizeObserver.observe(chartElement.value);
  }
  window.addEventListener('resize', resizeChart, { passive: true });
}

function unbindResize() {
  resizeObserver?.disconnect();
  resizeObserver = null;
  window.removeEventListener('resize', resizeChart);
  if (resizeFrame) {
    window.cancelAnimationFrame(resizeFrame);
    resizeFrame = 0;
  }
}

function resizeChart() {
  if (!chart.value) return;
  if (resizeFrame) window.cancelAnimationFrame(resizeFrame);
  resizeFrame = window.requestAnimationFrame(() => {
    chart.value?.resize();
    resizeFrame = 0;
  });
}

function disposeChart() {
  chart.value?.dispose();
  chart.value = null;
}
</script>

<template>
  <div ref="chartElement" class="dashboard-chart" role="img" :aria-label="ariaLabel"></div>
</template>
