<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue';

import { apiGet } from '../../api';
import { useAppContext } from '@app/context';
import { buildReadmeTypingSvgUrl, buildTemplateVariables, renderTemplate } from '../../composables/features/useSiteSettings';
import type { DashboardDistributionItem, DashboardSummary } from '../../types';
import { buildUiThemePalette } from '../../utils/uiTheme';
import { errorMessage } from '@shared/utils/errors';
import AppIcon from '@shared/components/AppIcon.vue';

const DashboardChart = defineAsyncComponent(() => import('./dashboard/DashboardChart.vue'));

type DashboardChartOption = Record<string, unknown>;
type DistributionWithPercent = DashboardDistributionItem & { percent: number };

const { currentUser, isWorkspaceDark, localIp, siteIdentity, dashboardHero, uiTheme } = useAppContext();

const summary = ref<DashboardSummary | null>(null);
const isLoading = ref(false);
const message = ref('');
const now = ref(new Date());
let clockTimer: number | undefined;

const heroClockDate = computed(() => formatHeroDate(now.value));
const heroClockTime = computed(() => formatClockTime(now.value));
const heroClockLabel = computed(() => `${heroClockDate.value} ${heroClockTime.value}`);
const generatedText = computed(() => (summary.value?.generatedAt ? formatTime(summary.value.generatedAt) : '--'));
const heroTemplateVariables = computed(() =>
  buildTemplateVariables({
    siteIdentity: siteIdentity.value,
    user: currentUser.value,
    localIp: localIp.value,
    generatedAt: generatedText.value,
    now: now.value,
  }),
);
const heroBadge = computed(() => renderTemplate(dashboardHero.value.badgeTemplate, heroTemplateVariables.value));
const heroTypingLines = computed(() =>
  [dashboardHero.value.line1Template, dashboardHero.value.line2Template]
    .map((template) => renderTemplate(template, heroTemplateVariables.value).trim())
    .filter(Boolean),
);
const heroTypingAlt = computed(() => heroTypingLines.value.join(' / '));
const heroTypingUrl = computed(() => buildReadmeTypingSvgUrl(dashboardHero.value, heroTypingLines.value));
const heroDescription = computed(() => renderTemplate(dashboardHero.value.descriptionTemplate, heroTemplateVariables.value));
const osTopList = computed(() => withPercent(summary.value?.assetDistribution.os ?? []));
const verificationList = computed(() => withPercent(summary.value?.assetDistribution.verification ?? []));
const userActiveRate = computed(() => {
  const users = summary.value?.users;
  return users?.total ? toPercent(users.active, users.total) : 0;
});
const availableUsers = computed(() => summary.value?.users.canLogin ?? summary.value?.users.active ?? 0);
const assetVerificationRate = computed(() => clampPercent(summary.value?.assets.verificationRate ?? 0));
const osTypeTotal = computed(() => sumDistribution(summary.value?.assetDistribution.os ?? []));
const groupRankingList = computed(() => {
  const groups = summary.value?.groupRanking ?? [];
  const max = Math.max(1, ...groups.map((group) => group.value));
  return groups.map((group) => ({
    ...group,
    percent: group.value ? Math.max(8, Math.round((group.value / max) * 100)) : 0,
  }));
});
const dashboardThemePalette = computed(() => buildUiThemePalette(uiTheme.value));
const chartColors = computed(() => {
  const dark = isWorkspaceDark.value;
  const charts = dark ? dashboardThemePalette.value.darkCharts : dashboardThemePalette.value.lightCharts;
  return {
    text: dark ? '#e5edf8' : '#0f2742',
    muted: dark ? '#9fb0c6' : '#64748b',
    axis: dark ? '#334155' : '#d8e3ef',
    grid: dark ? 'rgba(83, 104, 132, 0.38)' : 'rgba(148, 163, 184, 0.24)',
    track: dark ? 'rgba(71, 85, 105, 0.42)' : '#e8eff6',
    panel: dark ? '#111827' : '#ffffff',
    tooltipBg: dark ? 'rgba(15, 23, 42, 0.94)' : 'rgba(255, 255, 255, 0.96)',
    tooltipBorder: hexToRgba(charts[0], dark ? 0.28 : 0.22),
    teal: charts[0],
    blue: charts[1],
    yellow: '#f2b84b',
    red: '#e86f6f',
    tealAreaTop: hexToRgba(charts[0], 0.28),
    tealAreaBottom: hexToRgba(charts[0], 0.03),
    redAreaTop: 'rgba(232, 111, 111, 0.18)',
    redAreaBottom: 'rgba(232, 111, 111, 0.02)',
  };
});
const chartPalette = computed(() =>
  isWorkspaceDark.value ? dashboardThemePalette.value.darkCharts : dashboardThemePalette.value.lightCharts,
);

const userGaugeOption = computed<DashboardChartOption>(() =>
  buildGaugeOption({
    value: userActiveRate.value,
    detail: availableUsers.value,
    name: '可用用户',
    color: chartColors.value.blue,
  }),
);
const assetGaugeOption = computed<DashboardChartOption>(() =>
  buildGaugeOption({
    value: assetVerificationRate.value,
    detail: summary.value?.assets.total ?? 0,
    name: '资产总数',
    color: chartColors.value.teal,
  }),
);
const loginTrendOption = computed<DashboardChartOption>(() => {
  const points = summary.value?.loginTrend ?? [];
  const colors = chartColors.value;
  const hasData = points.some((point) => point.success || point.failed);

  return {
    color: [colors.teal, colors.red],
    textStyle: chartTextStyle(),
    tooltip: {
      trigger: 'axis',
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: colors.text, fontWeight: 700 },
      valueFormatter: (value: number | string) => `${value} 次`,
    },
    legend: {
      top: 0,
      right: 0,
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: colors.muted, fontWeight: 800 },
    },
    grid: { left: 8, right: 14, top: 38, bottom: 8, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map((point) => point.date),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: colors.axis } },
      axisLabel: { color: colors.muted, fontSize: 11, fontWeight: 700 },
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: colors.muted, fontSize: 11, fontWeight: 700 },
      splitLine: { lineStyle: { color: colors.grid, type: 'dashed' } },
    },
    series: [
      {
        name: '成功',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        showSymbol: points.length <= 8,
        data: points.map((point) => point.success),
        lineStyle: { width: 3, color: colors.teal },
        itemStyle: { color: colors.teal, borderColor: colors.panel, borderWidth: 2 },
        areaStyle: { color: linearGradient(colors.tealAreaTop, colors.tealAreaBottom) },
      },
      {
        name: '失败',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        showSymbol: points.length <= 8,
        data: points.map((point) => point.failed),
        lineStyle: { width: 3, color: colors.red },
        itemStyle: { color: colors.red, borderColor: colors.panel, borderWidth: 2 },
        areaStyle: { color: linearGradient(colors.redAreaTop, colors.redAreaBottom) },
      },
    ],
    graphic: hasData ? [] : emptyGraphic('暂无访问量数据'),
  };
});
const osTypePieOption = computed<DashboardChartOption>(() => {
  const colors = chartColors.value;
  const data = osTopList.value.map((item, index) => ({
    name: item.label,
    value: item.value,
    itemStyle: { color: chartPalette.value[index % chartPalette.value.length] },
  }));

  return {
    color: chartPalette.value,
    textStyle: chartTextStyle(),
    tooltip: {
      trigger: 'item',
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: colors.text, fontWeight: 700 },
      formatter: (params: { name: string; value: number; percent: number }) =>
        `${params.name}<br/>${formatNumber(params.value)} 台 (${Math.round(params.percent)}%)`,
    },
    legend: {
      bottom: 0,
      left: 'center',
      type: 'scroll',
      itemWidth: 10,
      itemHeight: 10,
      textStyle: { color: colors.muted, fontWeight: 800 },
      formatter: (name: string) => {
        const item = osTopList.value.find((entry) => entry.label === name);
        return item ? `${name} ${item.percent}%` : name;
      },
    },
    graphic: data.length
      ? [
          {
            type: 'text',
            left: 'center',
            top: '35%',
            style: {
              text: `${formatNumber(osTypeTotal.value)}\n系统类型`,
              fill: colors.text,
              fontSize: 18,
              fontWeight: 900,
              lineHeight: 24,
              textAlign: 'center',
            },
          },
        ]
      : emptyGraphic('暂无系统类型数据'),
    series: [
      {
        name: '系统类型',
        type: 'pie',
        radius: ['56%', '76%'],
        center: ['50%', '42%'],
        avoidLabelOverlap: true,
        minAngle: 8,
        itemStyle: {
          borderColor: colors.panel,
          borderRadius: 6,
          borderWidth: 3,
        },
        label: { show: false },
        labelLine: { show: false },
        data,
      },
    ],
  };
});
const verificationBarOption = computed<DashboardChartOption>(() => {
  const colors = chartColors.value;
  const data = verificationList.value.map((item, index) => ({
    value: item.percent,
    rawValue: item.value,
    itemStyle: { color: verificationColor(item.label, index) },
  }));

  return {
    textStyle: chartTextStyle(),
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'shadow' },
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: colors.text, fontWeight: 700 },
      formatter: (params: Array<{ name: string; value: number; data?: { rawValue?: number } }>) => {
        const item = params[0];
        return `${item.name}<br/>${formatNumber(item.data?.rawValue ?? 0)} 台 (${item.value}%)`;
      },
    },
    grid: { left: 8, right: 58, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'value',
      max: 100,
      axisLabel: { show: false },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: verificationList.value.map((item) => item.label),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: colors.muted, fontSize: 12, fontWeight: 800 },
    },
    series: [
      {
        type: 'bar',
        data,
        barWidth: 14,
        showBackground: true,
        backgroundStyle: { color: colors.track, borderRadius: 8 },
        itemStyle: { borderRadius: [0, 8, 8, 0] },
        label: {
          show: true,
          position: 'right',
          color: colors.text,
          fontSize: 12,
          fontWeight: 900,
          formatter: (params: { value: number }) => `${params.value}%`,
        },
      },
    ],
    graphic: data.length ? [] : emptyGraphic('暂无验证状态数据'),
  };
});

onMounted(() => {
  loadSummary();
  clockTimer = window.setInterval(() => {
    now.value = new Date();
  }, 1000);
});

onUnmounted(() => {
  if (clockTimer !== undefined) window.clearInterval(clockTimer);
});

async function loadSummary() {
  if (isLoading.value) return;
  isLoading.value = true;
  message.value = '';
  try {
    summary.value = await apiGet<DashboardSummary>('/api/dashboard/summary/');
  } catch (error) {
    message.value = errorMessage(error);
  } finally {
    isLoading.value = false;
  }
}

function withPercent(items: DashboardDistributionItem[]): DistributionWithPercent[] {
  const total = items.reduce((sum, item) => sum + item.value, 0);
  return items.map((item) => ({
    ...item,
    percent: total ? Math.round((item.value / total) * 100) : 0,
  }));
}

function buildGaugeOption(params: { value: number; detail: number; name: string; color: string }): DashboardChartOption {
  const colors = chartColors.value;
  return {
    textStyle: chartTextStyle(),
    tooltip: {
      formatter: () => `${params.name}<br/>${params.value}%`,
      backgroundColor: colors.tooltipBg,
      borderColor: colors.tooltipBorder,
      borderWidth: 1,
      textStyle: { color: colors.text, fontWeight: 700 },
    },
    series: [
      {
        type: 'gauge',
        radius: '84%',
        center: ['50%', '50%'],
        startAngle: 90,
        endAngle: -270,
        min: 0,
        max: 100,
        pointer: { show: false },
        progress: {
          show: true,
          roundCap: true,
          width: 11,
          itemStyle: { color: params.color },
        },
        axisLine: {
          roundCap: true,
          lineStyle: {
            width: 11,
            color: [[1, colors.track]],
          },
        },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        anchor: { show: false },
        title: {
          offsetCenter: [0, '22%'],
          color: colors.muted,
          fontSize: 11,
          fontWeight: 900,
        },
        detail: {
          offsetCenter: [0, '-4%'],
          color: colors.text,
          fontSize: 24,
          fontWeight: 900,
          lineHeight: 26,
          valueAnimation: true,
          formatter: () => formatNumber(params.detail),
        },
        data: [{ value: params.value, name: params.name }],
      },
    ],
  };
}

function chartTextStyle() {
  return {
    fontFamily: 'Inter, "Microsoft YaHei", "PingFang SC", Arial, sans-serif',
  };
}

function linearGradient(top: string, bottom: string) {
  return {
    type: 'linear',
    x: 0,
    y: 0,
    x2: 0,
    y2: 1,
    colorStops: [
      { offset: 0, color: top },
      { offset: 1, color: bottom },
    ],
  };
}

function hexToRgba(hex: string, alpha: number) {
  const value = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`;
}

function emptyGraphic(text: string) {
  return [
    {
      type: 'text',
      left: 'center',
      top: 'middle',
      style: {
        text,
        fill: chartColors.value.muted,
        fontSize: 13,
        fontWeight: 800,
        textAlign: 'center',
      },
    },
  ];
}

function verificationColor(label: string, index: number) {
  const colors = chartColors.value;
  if (/失败|异常|failed|error/i.test(label)) return colors.red;
  if (/未|unverified|pending/i.test(label)) return colors.yellow;
  if (/已|成功|verified|success/i.test(label)) return colors.teal;
  return chartPalette.value[index % chartPalette.value.length];
}

function sumDistribution(items: DashboardDistributionItem[]) {
  return items.reduce((sum, item) => sum + item.value, 0);
}

function toPercent(value: number, total: number) {
  return total ? clampPercent(Math.round((value / total) * 100)) : 0;
}

function clampPercent(value: number) {
  return Math.min(100, Math.max(0, Math.round(value)));
}

function formatNumber(value: number) {
  return new Intl.NumberFormat('zh-CN').format(value);
}

function padTimeUnit(value: number) {
  return String(value).padStart(2, '0');
}

function formatHeroDate(value: Date) {
  const weekdayLabels = ['日', '一', '二', '三', '四', '五', '六'];
  return `${value.getFullYear()}年${padTimeUnit(value.getMonth() + 1)}月${padTimeUnit(value.getDate())}日 星期${weekdayLabels[value.getDay()]}`;
}

function formatClockTime(value: Date) {
  return `${padTimeUnit(value.getHours())}:${padTimeUnit(value.getMinutes())}:${padTimeUnit(value.getSeconds())}`;
}

function formatTime(value: string | null) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 19);
  return `${date.getFullYear()}-${padTimeUnit(date.getMonth() + 1)}-${padTimeUnit(date.getDate())} ${padTimeUnit(date.getHours())}:${padTimeUnit(date.getMinutes())}`;
}

function statusText(status: string) {
  return status === 'success' ? '成功' : '失败';
}

function cardIcon(key: string) {
  const icons: Record<string, 'users' | 'server' | 'monitor' | 'alert'> = {
    users: 'users',
    assets: 'server',
    sessions: 'monitor',
    failed: 'alert',
  };
  return icons[key] ?? 'dashboard';
}

defineExpose({
  refresh: loadSummary,
});
</script>

<template>
  <section class="dashboard-page">
    <header class="dashboard-hero">
      <div class="dashboard-hero-copy">
        <span>{{ heroBadge }}</span>
        <h1 class="dashboard-typing-title">
          <img :src="heroTypingUrl" :alt="heroTypingAlt" />
        </h1>
        <p>{{ heroDescription }}</p>
      </div>
      <time class="dashboard-hero-clock" :datetime="now.toISOString()" :aria-label="heroClockLabel">
        <span>{{ heroClockDate }}</span>
        <strong>{{ heroClockTime }}</strong>
      </time>
    </header>

    <p v-if="message" class="dashboard-message">{{ message }}</p>

    <div v-if="summary" class="dashboard-content">
      <div class="dashboard-card-grid">
        <article class="dashboard-stat-card dashboard-egress-card" :class="{ error: summary.egressNetwork.status !== 'ok' }">
          <div class="dashboard-egress-info">
            <span>出口网络</span>
            <strong>{{ summary.egressNetwork.ip || '--' }}</strong>
            <div class="dashboard-egress-meta">
              <em>{{ summary.egressNetwork.status === 'ok' ? summary.egressNetwork.isp || '运营商未知' : '探测异常' }}</em>
              <small>{{ summary.egressNetwork.location || '位置未知' }}</small>
            </div>
          </div>
          <i><AppIcon name="globe" :size="22" /></i>
        </article>
        <article v-for="card in summary.cards" :key="card.key" class="dashboard-stat-card" :class="`tone-${card.tone}`">
          <div>
            <span>{{ card.label }}</span>
            <strong>{{ formatNumber(card.value) }}</strong>
            <em>{{ card.changeLabel }}</em>
          </div>
          <i><AppIcon :name="cardIcon(card.key)" :size="22" /></i>
        </article>
      </div>

      <div class="dashboard-main-grid">
        <article class="dashboard-panel dashboard-user-panel">
          <header>
            <div>
              <h2>用户数据</h2>
              <span>活跃率 {{ userActiveRate }}%</span>
            </div>
            <AppIcon name="user" :size="20" />
          </header>
          <div class="dashboard-ring-wrap">
            <DashboardChart class="dashboard-ring-chart" :option="userGaugeOption" aria-label="用户活跃率" />
          </div>
          <div class="dashboard-split-metrics">
            <span><strong>{{ summary.users.staff }}</strong> 管理员</span>
            <span><strong>{{ summary.users.disabled }}</strong> 已停用</span>
            <span><strong>{{ summary.users.newThisMonth }}</strong> 本月新增</span>
          </div>
        </article>

        <article class="dashboard-panel dashboard-asset-panel">
          <header>
            <div>
              <h2>资产数据</h2>
              <span>{{ assetVerificationRate }}% 已验证</span>
            </div>
            <AppIcon name="server" :size="20" />
          </header>
          <div class="dashboard-ring-wrap">
            <DashboardChart class="dashboard-ring-chart" :option="assetGaugeOption" aria-label="资产验证率" />
          </div>
          <div class="dashboard-split-metrics">
            <span><strong>{{ summary.assets.cpuCores }}</strong> CPU 核</span>
            <span><strong>{{ summary.assets.memoryGb }}</strong> GB 内存</span>
            <span><strong>{{ summary.assets.credentials }}</strong> 凭据</span>
          </div>
        </article>

        <article class="dashboard-panel dashboard-trend-panel">
          <header>
            <div>
              <h2>访问量</h2>
              <span>近 7 天登录趋势</span>
            </div>
            <AppIcon name="gauge" :size="20" />
          </header>
          <DashboardChart class="dashboard-trend-chart" :option="loginTrendOption" aria-label="近 7 天访问量趋势" />
        </article>
      </div>

      <div class="dashboard-lower-grid">
        <article class="dashboard-panel dashboard-bars-panel">
          <header>
            <div>
              <h2>资产类型占比</h2>
              <span>按系统类型统计</span>
            </div>
            <AppIcon name="hardDrive" :size="20" />
          </header>
          <DashboardChart class="dashboard-pie-chart" :option="osTypePieOption" aria-label="系统类型占比" />
          <div class="dashboard-distribution-list compact">
            <div v-for="item in osTopList" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
              <i><b :style="{ width: `${item.percent}%` }"></b></i>
            </div>
          </div>
        </article>

        <article class="dashboard-panel dashboard-verification-panel">
          <header>
            <div>
              <h2>验证状态</h2>
              <span>资产可用性概览</span>
            </div>
            <AppIcon name="shield" :size="20" />
          </header>
          <DashboardChart class="dashboard-bar-chart" :option="verificationBarOption" aria-label="资产验证状态" />
          <div class="dashboard-verification-summary">
            <span v-for="(item, index) in verificationList" :key="item.label">
              <em :style="{ backgroundColor: verificationColor(item.label, index) }"></em>
              {{ item.label }} {{ item.value }}
            </span>
          </div>
        </article>

        <article class="dashboard-panel dashboard-ranking-panel">
          <header>
            <div>
              <h2>资产分组排行</h2>
              <span>Top {{ summary.groupRanking.length }}</span>
            </div>
            <AppIcon name="folder" :size="20" />
          </header>
          <div class="dashboard-ranking-list">
            <div v-for="(group, index) in groupRankingList" :key="group.id">
              <em>{{ index + 1 }}</em>
              <span>
                <strong>{{ group.label }}</strong>
                <i><b :style="{ width: `${group.percent}%` }"></b></i>
              </span>
              <strong>{{ group.value }}</strong>
            </div>
            <p v-if="!groupRankingList.length">暂无资产分组数据</p>
          </div>
        </article>

        <article class="dashboard-panel dashboard-recent-panel">
          <header>
            <div>
              <h2>最近登录</h2>
              <span>最新 {{ summary.recentLogins.length }} 条记录</span>
            </div>
            <AppIcon name="bell" :size="20" />
          </header>
          <div class="dashboard-login-list">
            <div v-for="log in summary.recentLogins" :key="log.id">
              <span class="dashboard-login-status" :class="log.status">{{ statusText(log.status) }}</span>
              <strong>{{ log.userDisplay || log.username || '-' }}</strong>
              <em>{{ log.ipAddress || '-' }}</em>
              <time>{{ formatTime(log.createdAt) }}</time>
            </div>
            <p v-if="!summary.recentLogins.length">暂无登录记录</p>
          </div>
        </article>
      </div>

      <footer class="dashboard-footer">数据更新时间 {{ generatedText }}</footer>
    </div>

    <div v-else-if="isLoading" class="dashboard-loading">正在加载仪表盘...</div>
  </section>
</template>
