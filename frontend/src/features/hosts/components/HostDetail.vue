<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, toRef } from 'vue';
import { ElMessageBox } from 'element-plus';
import { useAppContext } from '@app/context';
import AppIcon from '@shared/components/AppIcon.vue';
import DashboardChart from '../../../components/tools/dashboard/DashboardChart.vue';
import type { ManagedHost } from '../types';
import { containerActionLabels, useHostContainerOperations } from '../composables/useHostContainerOperations';
import { useDockerResources, type DockerResourceTab } from '../composables/useDockerResources';
import { formatMonitorBytes as bytes, formatUptime, systemDisk, useHostMonitor } from '../composables/useHostMonitor';
import { gaugeOption, trendOption } from '../utils/monitorCharts';
import { dockerField, imageColumns, imageReferences, imageValue, shortDockerId } from '../utils/dockerResources';
import '../../../styles/tools/host/detail.css';

const props = defineProps<{ host: ManagedHost }>();
const emit = defineEmits<{ terminal: [host: ManagedHost] }>();
const { isWorkspaceDark, isLocked, isAuthenticated, canUsePageAction } = useAppContext();
const enabled = computed(() => !isLocked.value && isAuthenticated.value && canUsePageAction('hosts', 'terminal'));
const refreshIntervalSeconds = ref(10);
const refreshIntervals = [10, 15, 20];
const { snapshot, history, error, updatedAt, supported, active, refresh } = useHostMonitor(toRef(props, 'host'), enabled, undefined, refreshIntervalSeconds);
const docker = reactive(useDockerResources(computed(() => props.host.id), computed(() => enabled.value && supported.value)));
const containers = computed(() => docker.data.containers);
const dockerData = computed(() => docker.data[docker.activeTab]);
const visibleImageColumns = computed(() => imageColumns(docker.data.images?.images ?? []));
function refreshAll() { void refresh(); }
const reduceMotion = ref(false);
let motionQuery: MediaQueryList | null = null;
const onMotion = () => { reduceMotion.value = motionQuery?.matches ?? false; };
onMounted(() => {
  motionQuery = window.matchMedia?.('(prefers-reduced-motion: reduce)') ?? null;
  onMotion();
  motionQuery?.addEventListener('change', onMotion);
});
const disk = computed(() => systemDisk(snapshot.value));
const detailMetrics = ref(new Set<string>());
function toggleMetric(metric: string) {
  const next = new Set(detailMetrics.value);
  if (next.has(metric)) next.delete(metric);
  else next.add(metric);
  detailMetrics.value = next;
}
const cpuLoads = computed(() => [
  { label: '1 分钟', value: snapshot.value?.cpu.load1 },
  { label: '5 分钟', value: snapshot.value?.cpu.load5 },
  { label: '15 分钟', value: snapshot.value?.cpu.load15 },
]);
const memoryDetails = computed(() => [
  ['总内存', bytes(snapshot.value?.memory.totalBytes)],
  ['已使用', bytes(snapshot.value?.memory.usedBytes)],
  ['可用', bytes(snapshot.value?.memory.availableBytes)],
  ['缓存', bytes(snapshot.value?.memory.cacheBytes)],
  ['Swap', snapshot.value?.swap ? `${bytes(snapshot.value.swap.usedBytes)} / ${bytes(snapshot.value.swap.totalBytes)}` : '--'],
]);
const latestNetwork = computed(() => history.value[history.value.length - 1]);
const gauges = computed(() => [
  { title: 'CPU 使用率', icon: 'cpu' as const, color: '#5b8ff9', value: snapshot.value?.cpu.usagePercent ?? null, footer: snapshot.value ? `${snapshot.value.cpu.cores} 核心 · ${snapshot.value.system.arch}` : '等待采集' },
  { title: '内存使用', icon: 'server' as const, color: '#14b8a6', value: snapshot.value?.memory.usagePercent ?? null, footer: snapshot.value ? `${bytes(snapshot.value.memory.usedBytes)} / ${bytes(snapshot.value.memory.totalBytes)}` : '等待采集' },
  { title: '系统磁盘', icon: 'hardDrive' as const, color: '#a78bfa', value: disk.value?.usagePercent ?? null, footer: disk.value ? `${bytes(disk.value.usedBytes)} / ${bytes(disk.value.totalBytes)}` : '暂无磁盘信息' },
]);
const gaugeCards = computed(() => gauges.value.map((gauge) => ({ ...gauge, option: gaugeOption(gauge.value, gauge.color, isWorkspaceDark.value, reduceMotion.value) })));
const resourceChart = computed(() => trendOption(history.value, false, isWorkspaceDark.value, reduceMotion.value));
const networkChart = computed(() => trendOption(history.value, true, isWorkspaceDark.value, reduceMotion.value));
const runningCount = computed(() => containers.value?.containers.filter((item) => item.state === 'running').length ?? 0);
const dockerTabs: Array<{ key: DockerResourceTab; label: string }> = [{ key: 'containers', label: 'containers' }, { key: 'images', label: 'images' }, { key: 'networks', label: 'networks' }, { key: 'volumes', label: 'volumes' }];
const statusLabel = computed(() => !supported.value ? '暂不支持监控' : error.value ? '连接异常' : snapshot.value ? '在线' : '连接中');
const facts = computed(() => [
  ['操作系统', snapshot.value?.system.os || props.host.systemType || props.host.os],
  ['内核版本', snapshot.value?.system.kernel || '-'],
  ['系统架构', snapshot.value?.system.arch || props.host.systemArch || '-'],
  ['主机名称', snapshot.value?.system.hostname || props.host.machineName || '-'],
  ['CPU 型号', snapshot.value?.system.cpuModel || '-'],
  ['CPU 核心', snapshot.value ? `${snapshot.value.cpu.cores} 核` : '-'],
  ['主机时间', snapshot.value?.system.hostTime || '-'],
  ['运行时间', formatUptime(snapshot.value?.system.uptimeSeconds)],
  ['内存可用', bytes(snapshot.value?.memory.availableBytes)],
  ['内存缓存', bytes(snapshot.value?.memory.cacheBytes)],
  ['累计下行', snapshot.value ? bytes(snapshot.value.network.reduce((total, item) => total + (item.rxBytes ?? 0), 0)) : '--'],
  ['累计上行', snapshot.value ? bytes(snapshot.value.network.reduce((total, item) => total + (item.txBytes ?? 0), 0)) : '--'],
]);
const management = computed(() => [
  { label: 'Swap', value: snapshot.value?.swap ? snapshot.value.swap.available ? `${bytes(snapshot.value.swap.usedBytes)} / ${bytes(snapshot.value.swap.totalBytes)}` : '未启用' : '--', icon: 'server' as const },
  { label: 'SSH 连接端口', value: String(snapshot.value?.management?.sshPort ?? props.host.port ?? 22), icon: 'terminal' as const },
  { label: 'DNS 服务器', value: snapshot.value?.management?.dnsServers.join(' / ') || '-', icon: 'globe' as const },
  { label: 'TCP 拥塞算法', value: snapshot.value?.management?.tcpCongestionControl || '-', icon: 'network' as const },
  { label: 'IPv4 / IPv6', value: snapshot.value?.management ? `${snapshot.value.management.ipv4Enabled ? '已启用' : '未启用'} / ${snapshot.value.management.ipv6Enabled ? '已启用' : '未启用'}` : '--', icon: 'link' as const },
  { label: 'BBR 状态', value: snapshot.value?.management?.bbrEnabled == null ? '未知' : snapshot.value.management.bbrEnabled ? '已启用' : '未启用', icon: 'zap' as const },
]);

const { operationBusy, operationError, operationMessage, logsOpen, logsLoading, logsName, logs, logsError, logsTruncated, control, showLogs, closeLogs, enterContainer } = useHostContainerOperations(
  toRef(props, 'host'), enabled, docker.refreshContainers,
  (container, action) => ElMessageBox.confirm(`确定${containerActionLabels[action]}容器「${container.name}」吗？${action !== 'start' ? '这可能中断容器内正在运行的服务。' : ''}`, `${containerActionLabels[action]}容器`, { confirmButtonText: `确认${containerActionLabels[action]}`, cancelButtonText: '取消', type: 'warning' }),
);
onBeforeUnmount(() => { motionQuery?.removeEventListener('change', onMotion); });
</script>

<template>
  <div class="host-detail">
    <header class="host-detail-header">
      <div class="host-detail-identity">
        <div class="host-detail-server"><AppIcon name="server" :size="28" /></div>
        <div><div class="host-detail-title"><h2>{{ host.name }}</h2><el-tag :type="error || !supported ? 'info' : 'success'" size="small" effect="light">{{ statusLabel }}</el-tag></div><p>{{ host.privateIp }}<span v-if="host.publicIp"> · 公网 {{ host.publicIp }}</span><span> · {{ snapshot?.system.os || host.systemType || host.os }}</span></p></div>
      </div>
      <div class="host-detail-header-actions"><span>{{ formatUptime(snapshot?.system.uptimeSeconds) }}</span><div class="host-refresh-interval"><span>时间颗粒度</span><el-select v-model="refreshIntervalSeconds" aria-label="监控刷新间隔" size="small" :disabled="!active"><el-option v-for="seconds in refreshIntervals" :key="seconds" :label="`${seconds}s`" :value="seconds" /></el-select></div><el-button type="primary" :disabled="!active" @click="refreshAll"><AppIcon name="refresh" :size="15" />立即刷新</el-button></div>
    </header>
    <div class="host-detail-caption"><strong>实时监控</strong><span><i :class="{ paused: !active }"></i>{{ active ? `每 ${refreshIntervalSeconds} 秒自动刷新` : '监控已暂停' }} · {{ updatedAt ? `更新于 ${new Date(updatedAt).toLocaleTimeString('zh-CN', { hour12: false })}` : '等待首次采集' }} · 最近 15 分钟</span></div>
    <el-alert v-if="!supported" title="Windows 主机暂不支持资源与 Docker 监控，以下仅展示已保存的资产信息。" type="info" :closable="false" show-icon />
    <el-alert v-if="error" :title="`监控读取失败：${error}。保留最近一次数据，后续自动重试。`" type="error" :closable="false" show-icon />
    <div class="host-detail-metrics">
      <el-card v-for="gauge in gaugeCards" :key="gauge.title" shadow="never" class="host-metric-card"><div class="host-card-label"><span>{{ gauge.title }}</span><button type="button" class="host-metric-toggle" :aria-label="gauge.title + '切换视图'" :aria-pressed="detailMetrics.has(gauge.icon)" @click="toggleMetric(gauge.icon)"><AppIcon :name="gauge.icon" :size="17" /></button></div><div class="host-metric-viewport"><template v-if="!detailMetrics.has(gauge.icon)"><DashboardChart v-if="active" class="host-gauge" :aria-label="gauge.title" :option="gauge.option" /><div v-else class="host-gauge-placeholder">{{ gauge.value == null ? '--' : `${gauge.value}%` }}</div></template><div v-if="detailMetrics.has(gauge.icon)" class="host-metric-details">
          <template v-if="gauge.icon === 'cpu'">
            <div class="host-cpu-loads"><div v-for="load in cpuLoads" :key="load.label"><b>{{ load.value?.toFixed(2) ?? '--' }}</b><small>{{ load.label }}</small></div></div>
            <div class="host-metric-detail-heading">{{ snapshot?.cpu.cores ?? '--' }} CPU</div>
            <div v-for="core in snapshot?.cpu.perCore ?? []" :key="core.name" class="host-cpu-core"><span>{{ core.name }}</span><el-progress :percentage="core.usagePercent" :show-text="false" :stroke-width="6" /><span>{{ core.usagePercent.toFixed(1) }}%</span></div>
            <span v-if="!snapshot?.cpu.perCore?.length" class="host-metric-empty">暂无逐核数据</span>
          </template>
          <dl v-else-if="gauge.icon === 'server'" class="host-metric-facts"><div v-for="item in memoryDetails" :key="item[0]"><dt>{{ item[0] }}</dt><dd>{{ item[1] }}</dd></div></dl>
          <div v-else class="host-metric-disks"><div v-for="volume in snapshot?.disks ?? []" :key="volume.filesystem + volume.mountpoint"><div class="host-metric-detail-heading">{{ volume.mountpoint }} · {{ volume.filesystem }}</div><el-progress :percentage="volume.usagePercent" :stroke-width="6" /><small>{{ bytes(volume.usedBytes) }} / {{ bytes(volume.totalBytes) }} · 可用 {{ bytes(volume.availableBytes) }}</small></div><span v-if="!snapshot?.disks.length" class="host-metric-empty">暂无磁盘数据</span></div>
        </div></div><p>{{ gauge.footer }}</p></el-card>
      <el-card shadow="never" class="host-metric-card host-load-card"><div class="host-card-label"><span>系统负载</span><AppIcon name="gauge" :size="17" /></div><strong>{{ snapshot?.cpu.load1.toFixed(2) ?? '--' }}</strong><small>1 分钟平均负载</small><div class="host-load-values"><span>5 分钟<b>{{ snapshot?.cpu.load5.toFixed(2) ?? '--' }}</b></span><span>15 分钟<b>{{ snapshot?.cpu.load15.toFixed(2) ?? '--' }}</b></span></div><p>{{ snapshot ? `${snapshot.cpu.cores} 核心 · 负载参考` : '等待采集' }}</p></el-card>
      <el-card shadow="never" class="host-metric-card host-network-card"><div class="host-card-label"><span>网络吞吐</span><AppIcon name="network" :size="17" /></div><div class="host-network-rate"><small>↓ 下行</small><strong>{{ bytes(latestNetwork?.rx) }}<em>/s</em></strong></div><div class="host-network-rate upload"><small>↑ 上行</small><strong>{{ bytes(latestNetwork?.tx) }}<em>/s</em></strong></div><p>全部非回环网络接口</p></el-card>
    </div>
    <div class="host-detail-chart-grid">
      <el-card shadow="never" class="host-detail-card"><template #header><div class="host-section-heading"><h3>资源使用趋势</h3><span>CPU / 内存 / 系统磁盘</span></div></template><DashboardChart v-if="active" class="host-trend" aria-label="CPU 内存 磁盘动态曲线" :option="resourceChart" /><el-empty v-else description="监控暂停" :image-size="50" /></el-card>
      <el-card shadow="never" class="host-detail-card"><template #header><div class="host-section-heading"><h3>网络吞吐趋势</h3><span>实时上行 / 下行</span></div></template><DashboardChart v-if="active" class="host-trend" aria-label="网络动态曲线" :option="networkChart" /><el-empty v-else description="监控暂停" :image-size="50" /></el-card>
    </div>
    <div class="host-detail-info-grid">
      <el-card shadow="never" class="host-detail-card"><template #header><div class="host-section-heading"><h3>系统信息</h3><el-button text type="primary" :disabled="!enabled" @click="emit('terminal', host)"><AppIcon name="terminal" :size="15" />打开终端</el-button></div></template><dl class="host-facts"><div v-for="fact in facts" :key="fact[0]"><dt>{{ fact[0] }}</dt><dd>{{ fact[1] }}</dd></div></dl></el-card>
      <el-card shadow="never" class="host-detail-card"><template #header><div class="host-section-heading"><h3>系统管理</h3><span>只读状态 · 通过终端配置</span></div></template><div class="host-management-grid"><div v-for="item in management" :key="item.label"><AppIcon :name="item.icon" :size="20" /><span>{{ item.label }}<strong>{{ item.value }}</strong></span></div></div><div class="host-addresses"><span>内网 <b>{{ host.privateIp || '-' }}</b></span><span>公网 <b>{{ host.publicIp || '-' }}</b></span></div></el-card>
    </div>
    <el-card shadow="never" class="host-detail-card"><template #header><div class="host-section-heading"><h3>磁盘与文件系统</h3><span>{{ snapshot?.disks.length ?? 0 }} 个挂载点</span></div></template><el-table :data="snapshot?.disks ?? []" empty-text="暂无磁盘信息" class="host-detail-table"><el-table-column prop="filesystem" label="文件系统" min-width="150" show-overflow-tooltip /><el-table-column prop="mountpoint" label="挂载点" min-width="110" /><el-table-column prop="type" label="类型" width="100" /><el-table-column label="总容量" min-width="120"><template #default="{ row }">{{ bytes(row.totalBytes) }}</template></el-table-column><el-table-column label="已用 / 可用" min-width="190"><template #default="{ row }">{{ bytes(row.usedBytes) }} / {{ bytes(row.availableBytes) }}</template></el-table-column><el-table-column label="使用率" min-width="180"><template #default="{ row }"><el-progress :percentage="Math.min(100, Math.max(0, row.usagePercent))" :color="row.usagePercent > 90 ? '#f56c6c' : '#5b8ff9'" /></template></el-table-column></el-table></el-card>
    <el-card shadow="never" class="host-detail-card"><template #header><div class="host-docker-heading"><h3>Docker</h3><nav class="host-docker-tabs" aria-label="Docker 资源分类"><button v-for="tab in dockerTabs" :key="tab.key" type="button" :aria-current="docker.activeTab === tab.key ? 'page' : undefined" :disabled="!enabled || !supported" @click="docker.select(tab.key)">{{ tab.label }} <span>{{ docker.counts[tab.key] }}</span></button></nav><span v-if="docker.activeTab === 'containers'">启动、停止、重启均记录审计</span></div></template>
      <p v-if="docker.loading[docker.activeTab] && !dockerData" class="host-log-hint" role="status">正在加载 {{ docker.activeTab }}…</p>
      <el-alert v-if="docker.errors[docker.activeTab] || dockerData?.available === false" :title="docker.errors[docker.activeTab] || dockerData?.reason || 'Docker 服务不可用'" type="warning" :closable="false" show-icon />
      <el-alert v-if="operationBusy" title="容器操作进行中…" type="info" :closable="false" show-icon /><el-alert v-if="operationError" :title="operationError" type="error" :closable="false" show-icon /><el-alert v-if="operationMessage" :title="operationMessage" type="success" :closable="false" show-icon />
      <template v-if="docker.activeTab === 'containers'">
        <p>{{ containers ? `${runningCount} 运行 / ${containers.containers.length} 总计` : '—' }}</p>
      <el-table :data="containers?.containers ?? []" empty-text="暂无容器" class="host-detail-table"><el-table-column label="名称 / 镜像" min-width="210" show-overflow-tooltip><template #default="{ row }"><div class="host-container-name"><strong>{{ row.name }}</strong><small>{{ row.image }}</small></div></template></el-table-column><el-table-column label="状态" min-width="155"><template #default="{ row }"><el-tag :type="row.state === 'running' ? 'success' : 'info'" size="small">{{ row.state }}</el-tag><small class="host-container-status">{{ row.status }}</small></template></el-table-column><el-table-column label="端口" prop="ports" min-width="160" show-overflow-tooltip /><el-table-column label="CPU / 内存" min-width="140"><template #default="{ row }">{{ row.cpuPercent == null ? '--' : `${row.cpuPercent}%` }} / {{ bytes(row.memoryUsageBytes) }}</template></el-table-column><el-table-column label="操作" min-width="300"><template #default="{ row }"><div class="host-container-actions"><el-button v-if="row.state === 'exited' || row.state === 'created'" text type="primary" :disabled="operationBusy || !enabled" @click="control(row, 'start')">启动</el-button><el-button v-if="row.state === 'running'" text type="warning" :disabled="operationBusy || !enabled" @click="control(row, 'stop')">停止</el-button><el-button text type="primary" :disabled="operationBusy || !enabled || row.state === 'paused'" @click="control(row, 'restart')">重启</el-button><el-button text type="primary" :disabled="logsLoading || !enabled" @click="showLogs(row)">日志</el-button><el-button text type="primary" :disabled="row.state !== 'running' || !enabled" @click="enterContainer(row)">进入终端</el-button></div></template></el-table-column></el-table>
      </template>
      <el-table v-if="docker.activeTab === 'images'" :data="docker.data.images?.images ?? []" empty-text="暂无镜像" class="host-detail-table">
        <el-table-column v-for="column in visibleImageColumns" :key="column.key" :label="column.label" :min-width="column.minWidth">
          <template #default="{ row }">
            <div v-if="column.key === 'references'" class="host-docker-references"><span v-for="reference in imageReferences(row)" :key="reference" :title="reference">{{ reference }}</span><span v-if="!imageReferences(row).length">—</span></div>
            <span v-else-if="column.key === 'id'" :title="row.id">{{ shortDockerId(row.id) }}</span>
            <span v-else :title="imageValue(row, column.key)">{{ dockerField(imageValue(row, column.key)) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-table v-if="docker.activeTab === 'networks'" :data="docker.data.networks?.networks ?? []" empty-text="暂无网络" class="host-detail-table">
        <el-table-column label="NETWORK ID" min-width="160"><template #default="{ row }"><span :title="row.id">{{ shortDockerId(row.id) }}</span></template></el-table-column>
        <el-table-column prop="name" label="NAME" min-width="220" show-overflow-tooltip />
        <el-table-column prop="driver" label="DRIVER" min-width="140" />
        <el-table-column prop="scope" label="SCOPE" min-width="120" />
      </el-table>
      <el-table v-if="docker.activeTab === 'volumes'" :data="docker.data.volumes?.volumes ?? []" empty-text="暂无卷" class="host-detail-table"><el-table-column prop="name" label="名称" min-width="220" show-overflow-tooltip /><el-table-column prop="driver" label="驱动" width="160" /></el-table>
    </el-card>
    <el-dialog v-model="logsOpen" :title="`容器日志 · ${logsName}`" width="min(1000px, 94vw)" append-to-body destroy-on-close :close-on-click-modal="false" class="host-container-log-dialog" @close="closeLogs"><p class="host-log-hint">最近 200 行 · 最多显示 1 MiB · 关闭弹窗不会影响容器</p><el-alert v-if="logsError" :title="logsError" type="error" :closable="false" /><el-alert v-if="logsTruncated" title="日志过长，显示内容已截断。" type="warning" :closable="false" /><pre class="host-container-logs" role="log" :aria-busy="logsLoading">{{ logsLoading ? '正在读取日志…' : logs || (logsError ? '读取失败' : '暂无日志') }}</pre></el-dialog>
  </div>
</template>
