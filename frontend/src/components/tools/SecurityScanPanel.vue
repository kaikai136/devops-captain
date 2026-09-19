<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue';

import { appContextKey } from '@app/context';
import {
  cancelSecurityScanTask,
  createSecurityScanTask,
  deleteSecurityScanTask,
  exportSecurityScanTask,
  getSecurityScanSummary,
  getSecurityScanTask,
  listSecurityScanFindings,
  listSecurityScanTargets,
  listSecurityScanTasks,
  retryFailedSecurityScanTargets,
} from '../../services/securityScans';
import type {
  SecurityScanFinding,
  SecurityScanSeverity,
  SecurityScanStatus,
  SecurityScanSummary,
  SecurityScanTarget,
  SecurityScanTargetResult,
  SecurityScanTask,
  SecurityScanTaskDetail,
} from '../../types';
import { errorMessage } from '@shared/utils/errors';
import AppIcon from '@shared/components/AppIcon.vue';

const DEFAULT_PORTS = '21,22,23,25,53,80,110,139,143,443,445,3306,3389,5432,5900,6379,8080,8443,27017';
const emptyRiskCounts = { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
const statusLabels: Record<string, string> = {
  queued: '排队中',
  running: '扫描中',
  completed: '已完成',
  failed: '失败',
  canceled: '已取消',
  pending: '等待中',
  skipped: '已跳过',
};
const severityLabels: Record<SecurityScanSeverity, string> = { critical: '严重', high: '高危', medium: '中危', low: '低危', info: '提示' };
const categoryLabels: Record<string, string> = { baseline: '基线', port: '端口', cve: 'CVE' };
const severityOrder: SecurityScanSeverity[] = ['critical', 'high', 'medium', 'low', 'info'];

interface AssetRiskReportRow {
  id: number;
  index: number;
  hostName: string;
  hostIp: string;
  businessGroup: string;
  owner: string;
  coreAsset: string;
  riskTotal: number;
  riskType: string;
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

interface ImpactReportRow {
  key: string;
  index: number;
  title: string;
  severity: SecurityScanSeverity;
  riskType: string;
  affectedAssets: string;
  affectedAssetCount: number;
  occurrences: number;
}

type ReportTabKey = 'overview' | 'assets' | 'impact' | 'details';

const appContext = inject(appContextKey);
const canUsePageAction = appContext?.canUsePageAction ?? (() => true);
const showToast = appContext?.showToast ?? (() => undefined);
const requestConfirm = appContext?.requestConfirm;

const targets = ref<SecurityScanTarget[]>([]);
const tasks = ref<SecurityScanTask[]>([]);
const selectedTask = ref<SecurityScanTaskDetail | null>(null);
const selectedTaskId = ref<number | null>(null);
const summary = ref<SecurityScanSummary>({
  riskCounts: emptyRiskCounts,
  taskCounts: { total: 0, running: 0, failed: 0 },
  failedTargetCount: 0,
  latestTaskId: null,
  vulnerabilitySource: { onlineCveEnabled: false, nvdApiKeyConfigured: false, sources: [] },
});
const findings = ref<SecurityScanFinding[]>([]);
const findingsPage = ref(1);
const findingsTotal = ref(0);
const findingsHasNext = ref(false);
const isLoading = ref(false);
const isLoadingFindings = ref(false);
const isCreating = ref(false);
const isControlBusy = ref(false);
const isDrawerOpen = ref(false);
const keyword = ref('');
const statusFilter = ref('');
const findingKeyword = ref('');
const severityFilter = ref('');
const categoryFilter = ref('');
const targetResultFilter = ref('');
const targetKeyword = ref('');
const activeReportTab = ref<ReportTabKey>('overview');
const selectedTargetIds = ref<Set<number>>(new Set());
const taskName = ref('');
const portsInput = ref(DEFAULT_PORTS);
const scanBaseline = ref(true);
const scanPorts = ref(true);
const scanCve = ref(false);
let pollTimer: number | null = null;
let taskSelectionRequest = 0;

const filteredTargets = computed(() => {
  const term = targetKeyword.value.trim().toLowerCase();
  if (!term) return targets.value;
  return targets.value.filter((target) =>
    [target.name, target.privateIp, target.groupName, target.os, target.systemType, target.systemArch].some((value) => String(value || '').toLowerCase().includes(term)),
  );
});
const selectedTargets = computed(() => targets.value.filter((target) => selectedTargetIds.value.has(target.id)));
const targetResults = computed(() => selectedTask.value?.targetResults ?? []);
const canStartScan = computed(() => selectedTargetIds.value.size > 0 && (scanBaseline.value || scanPorts.value || scanCve.value) && !isCreating.value);
const hasRunningTask = computed(() => tasks.value.some((task) => task.status === 'queued' || task.status === 'running'));
const failedTargetsInSelectedTask = computed(() => targetResults.value.filter((target) => target.status === 'failed').length);
const selectedTaskCanCancel = computed(() => Boolean(selectedTask.value && ['queued', 'running'].includes(selectedTask.value.status)));
const selectedTaskRiskTotal = computed(() => (selectedTask.value ? riskTotal(selectedTask.value.riskCounts) : 0));
const sourceStatusText = computed(() => (summary.value.vulnerabilitySource.onlineCveEnabled ? '在线 CVE 已开启' : '在线 CVE 已关闭'));
const selectedTaskReportTime = computed(() => formatTime(selectedTask.value?.finishedAt || selectedTask.value?.startedAt || selectedTask.value?.createdAt || null));
const selectedTaskModulesText = computed(() => {
  if (!selectedTask.value) return '-';
  const modules = selectedTask.value.scanModules;
  const labels = [
    modules.baseline ? '基线检查' : '',
    modules.ports ? '端口风险' : '',
    modules.cve ? 'CVE 检查' : '',
  ].filter(Boolean);
  return labels.length ? labels.join(' / ') : '-';
});
const taskOptionsLabel = computed(() => (tasks.value.length ? `扫描任务 ${tasks.value.length} 个` : '暂无扫描任务'));
const findingsByTarget = computed(() => {
  const grouped = new Map<number, SecurityScanFinding[]>();
  for (const finding of findings.value) {
    const bucket = grouped.get(finding.targetResult) ?? [];
    bucket.push(finding);
    grouped.set(finding.targetResult, bucket);
  }
  return grouped;
});
const targetGroupByHostId = computed(() => {
  const grouped = new Map<number, string>();
  for (const target of targets.value) grouped.set(target.id, target.groupName || '-');
  return grouped;
});
const assetRiskRows = computed<AssetRiskReportRow[]>(() =>
  targetResults.value.map((target, index) => {
    const targetFindings = findingsByTarget.value.get(target.id) ?? [];
    const categories = uniqueStrings(targetFindings.map((finding) => categoryLabel(finding.category)));
    const total = riskTotal(target.riskCounts);
    return {
      id: target.id,
      index: index + 1,
      hostName: target.hostName || '-',
      hostIp: target.hostIp || '-',
      businessGroup: target.host ? targetGroupByHostId.value.get(target.host) || '-' : '-',
      owner: target.loginUser || '-',
      coreAsset: '否',
      riskTotal: total,
      riskType: categories.length ? categories.join(' / ') : total ? '风险项' : '无风险',
      critical: target.riskCounts.critical,
      high: target.riskCounts.high,
      medium: target.riskCounts.medium,
      low: target.riskCounts.low,
      info: target.riskCounts.info,
    };
  }),
);
const impactRows = computed<ImpactReportRow[]>(() => {
  const grouped = new Map<
    string,
    {
      title: string;
      severity: SecurityScanSeverity;
      categories: Set<string>;
      assets: Set<string>;
      occurrences: number;
    }
  >();
  for (const finding of findings.value) {
    const key = finding.title || `finding-${finding.id}`;
    const row = grouped.get(key) ?? {
      title: finding.title || '-',
      severity: finding.severity,
      categories: new Set<string>(),
      assets: new Set<string>(),
      occurrences: 0,
    };
    row.severity = higherSeverity(row.severity, finding.severity);
    row.categories.add(categoryLabel(finding.category));
    row.assets.add(finding.targetIp || finding.targetName || '-');
    row.occurrences += 1;
    grouped.set(key, row);
  }
  return [...grouped.entries()]
    .map(([key, row], index) => ({
      key,
      index: index + 1,
      title: row.title,
      severity: row.severity,
      riskType: [...row.categories].join(' / ') || '-',
      affectedAssets: [...row.assets].join(' '),
      affectedAssetCount: row.assets.size,
      occurrences: row.occurrences,
    }))
    .sort((left, right) => severityRank(left.severity) - severityRank(right.severity) || right.occurrences - left.occurrences || left.title.localeCompare(right.title, 'zh-Hans-CN'))
    .map((row, index) => ({ ...row, index: index + 1 }));
});
const reportTabs = computed<Array<{ key: ReportTabKey; label: string; count: number }>>(() => [
  { key: 'overview', label: '综述', count: selectedTaskRiskTotal.value },
  { key: 'assets', label: '资产风险统计', count: assetRiskRows.value.length },
  { key: 'impact', label: '漏洞影响统计', count: impactRows.value.length },
  { key: 'details', label: '漏洞详情', count: findingsTotal.value },
]);

onMounted(async () => {
  await refreshAll();
  startPolling();
});

onUnmounted(() => {
  stopPolling();
});

watch([severityFilter, categoryFilter, targetResultFilter], () => {
  void reloadFindings();
});

async function refreshAll() {
  isLoading.value = true;
  try {
    await Promise.all([loadTargets(), loadSummary(), loadTasks()]);
  } finally {
    isLoading.value = false;
  }
}

async function loadTargets() {
  try {
    targets.value = await listSecurityScanTargets();
  } catch (error) {
    showToast('目标主机加载失败', errorMessage(error), 'error');
  }
}

async function loadSummary() {
  try {
    summary.value = await getSecurityScanSummary();
    if (!summary.value.vulnerabilitySource.onlineCveEnabled) scanCve.value = false;
  } catch (error) {
    showToast('安全扫描概览加载失败', errorMessage(error), 'error');
  }
}

async function loadTasks() {
  try {
    tasks.value = await listSecurityScanTasks({ status: statusFilter.value, keyword: keyword.value.trim() });
    if (!tasks.value.length) {
      selectedTaskId.value = null;
      selectedTask.value = null;
      findings.value = [];
      findingsPage.value = 1;
      findingsTotal.value = 0;
      findingsHasNext.value = false;
      return;
    }
    if (!selectedTaskId.value || !tasks.value.some((task) => task.id === selectedTaskId.value)) selectedTaskId.value = tasks.value[0].id;
    if (selectedTaskId.value) {
      if (selectedTask.value) await refreshSelectedTaskSummary();
      else await selectTask(selectedTaskId.value, false);
    }
  } catch (error) {
    showToast('扫描任务加载失败', errorMessage(error), 'error');
  }
}

async function selectTask(taskId: number, showError = true) {
  const requestId = ++taskSelectionRequest;
  selectedTaskId.value = taskId;
  findings.value = [];
  findingsPage.value = 1;
  findingsTotal.value = 0;
  findingsHasNext.value = false;
  targetResultFilter.value = '';
  try {
    const detail = await getSecurityScanTask(taskId);
    if (requestId !== taskSelectionRequest || selectedTaskId.value !== taskId) return;
    selectedTask.value = detail;
    await loadFindings(taskId, 1, true, requestId);
  } catch (error) {
    if (requestId !== taskSelectionRequest || selectedTaskId.value !== taskId) return;
    selectedTask.value = null;
    if (showError) showToast('任务详情加载失败', errorMessage(error), 'error');
  }
}

async function refreshSelectedTaskSummary() {
  if (!selectedTaskId.value) return;
  try {
    selectedTask.value = await getSecurityScanTask(selectedTaskId.value);
  } catch {
    selectedTask.value = null;
  }
}

async function reloadFindings() {
  if (!selectedTaskId.value) return;
  findings.value = [];
  findingsPage.value = 1;
  await loadFindings(selectedTaskId.value, 1, true);
}

async function loadFindings(taskId = selectedTaskId.value, page = findingsPage.value + 1, replace = false, requestId = taskSelectionRequest) {
  if (!taskId || isLoadingFindings.value) return;
  isLoadingFindings.value = true;
  try {
    const payload = await listSecurityScanFindings(taskId, {
      page,
      pageSize: 50,
      severity: severityFilter.value,
      category: categoryFilter.value,
      hostId: targetResultFilter.value,
      keyword: findingKeyword.value.trim(),
    });
    if (requestId !== taskSelectionRequest || selectedTaskId.value !== taskId) return;
    findings.value = replace ? payload.results : [...findings.value, ...payload.results];
    findingsPage.value = payload.page;
    findingsTotal.value = payload.total;
    findingsHasNext.value = payload.hasNext;
  } catch (error) {
    if (requestId !== taskSelectionRequest || selectedTaskId.value !== taskId) return;
    if (replace) findings.value = [];
    showToast('风险明细加载失败', errorMessage(error), 'error');
  } finally {
    if (requestId === taskSelectionRequest && selectedTaskId.value === taskId) isLoadingFindings.value = false;
  }
}

function toggleTarget(targetId: number, checked: boolean) {
  const next = new Set(selectedTargetIds.value);
  if (checked) next.add(targetId);
  else next.delete(targetId);
  selectedTargetIds.value = next;
}

function toggleAllVisibleTargets(checked: boolean) {
  const next = new Set(selectedTargetIds.value);
  for (const target of filteredTargets.value) {
    if (checked) next.add(target.id);
    else next.delete(target.id);
  }
  selectedTargetIds.value = next;
}

async function startScan() {
  if (!canStartScan.value) return;
  isCreating.value = true;
  try {
    const task = await createSecurityScanTask({
      targetIds: [...selectedTargetIds.value],
      portsInput: portsInput.value,
      name: taskName.value.trim() || undefined,
      scanModules: { baseline: scanBaseline.value, ports: scanPorts.value, cve: scanCve.value },
    });
    isDrawerOpen.value = false;
    selectedTargetIds.value = new Set();
    taskName.value = '';
    await Promise.all([loadSummary(), loadTasks()]);
    await selectTask(task.id);
    showToast('扫描任务已创建', '后台正在执行安全巡检。', 'success');
  } catch (error) {
    showToast('扫描任务创建失败', errorMessage(error), 'error');
  } finally {
    isCreating.value = false;
  }
}

async function cancelSelectedTask() {
  if (!selectedTaskId.value || isControlBusy.value) return;
  isControlBusy.value = true;
  try {
    await cancelSecurityScanTask(selectedTaskId.value);
    await Promise.all([loadSummary(), loadTasks(), refreshSelectedTaskSummary()]);
    showToast('已请求取消', '当前主机扫描结束后会停止后续任务。', 'success');
  } catch (error) {
    showToast('取消任务失败', errorMessage(error), 'error');
  } finally {
    isControlBusy.value = false;
  }
}

async function retryFailedTargets() {
  if (!selectedTaskId.value || isControlBusy.value) return;
  isControlBusy.value = true;
  try {
    await retryFailedSecurityScanTargets(selectedTaskId.value);
    await Promise.all([loadSummary(), loadTasks(), refreshSelectedTaskSummary(), reloadFindings()]);
    showToast('失败主机已重新排队', '后台正在重新扫描失败目标。', 'success');
  } catch (error) {
    showToast('重试失败主机失败', errorMessage(error), 'error');
  } finally {
    isControlBusy.value = false;
  }
}

async function exportTask(format: 'csv' | 'json') {
  if (!selectedTaskId.value) return;
  try {
    const blob = await exportSecurityScanTask(selectedTaskId.value, format);
    downloadBlob(blob, `security-scan-${selectedTaskId.value}.${format}`);
  } catch (error) {
    showToast('报告导出失败', errorMessage(error), 'error');
  }
}

function removeSelectedTask() {
  if (!selectedTaskId.value) return;
  const taskId = selectedTaskId.value;
  const run = async () => {
    try {
      await deleteSecurityScanTask(taskId);
      selectedTaskId.value = null;
      selectedTask.value = null;
      findings.value = [];
      await Promise.all([loadSummary(), loadTasks()]);
      showToast('扫描任务已删除', '历史记录和扫描结果已移除。', 'success');
    } catch (error) {
      showToast('删除失败', errorMessage(error), 'error');
    }
  };
  if (requestConfirm) requestConfirm('删除扫描任务', '删除后将同时移除该任务下的主机结果和风险明细。', '删除', run);
  else void run();
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(async () => {
    if (hasRunningTask.value) {
      await Promise.all([loadSummary(), loadTasks()]);
      if (selectedTaskId.value) await reloadFindings();
    }
  }, 5000);
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function riskTotal(counts: SecurityScanTask['riskCounts']) {
  return counts.critical + counts.high + counts.medium + counts.low + counts.info;
}

function uniqueStrings(values: string[]) {
  return [...new Set(values.filter(Boolean))];
}

function severityRank(severity: SecurityScanSeverity) {
  const index = severityOrder.indexOf(severity);
  return index === -1 ? severityOrder.length : index;
}

function higherSeverity(left: SecurityScanSeverity, right: SecurityScanSeverity) {
  return severityRank(left) <= severityRank(right) ? left : right;
}

function statusLabel(status: SecurityScanStatus | SecurityScanTargetResult['status']) {
  return statusLabels[status] ?? status;
}

function formatTime(value: string | null) {
  if (!value) return '-';
  return new Date(value).toLocaleString();
}

function severityClass(severity: SecurityScanFinding['severity']) {
  return `severity-${severity}`;
}

function categoryLabel(category: string) {
  return categoryLabels[category] ?? category;
}

function detectionType(finding: SecurityScanFinding) {
  if (finding.category === 'baseline') return '基线检查';
  if (finding.category === 'port') return '端口风险扫描';
  if (finding.category === 'cve') return 'CVE 检查';
  return `${categoryLabel(finding.category)}扫描`;
}

function optionalFindingField(finding: SecurityScanFinding, field: 'description' | 'evidence') {
  const extended = finding as SecurityScanFinding & Partial<Record<'description' | 'evidence', string>>;
  return extended[field] || '';
}

function findingDescription(finding: SecurityScanFinding) {
  return optionalFindingField(finding, 'description') || finding.cwe || finding.source || '-';
}

function findingEvidence(finding: SecurityScanFinding) {
  const explicitEvidence = optionalFindingField(finding, 'evidence');
  if (explicitEvidence) return explicitEvidence;
  return [finding.cveId, finding.packageName, finding.currentVersion, finding.service, finding.port ? `${finding.targetIp}:${finding.port}` : ''].filter(Boolean).join(' / ') || '-';
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
</script>

<template>
  <section class="security-scan-page">
    <header class="security-workbench-header">
      <div>
        <h2>安全扫描</h2>
        <p>面向已验证 Linux SSH 主机的只读风险巡检报告。</p>
      </div>
      <div class="security-workbench-actions">
        <el-button v-if="canUsePageAction('securityScan', 'scan')" type="primary" @click="isDrawerOpen = true"><AppIcon name="scan" :size="16" />新建巡检</el-button>
        <el-button v-if="canUsePageAction('securityScan', 'refresh')" :loading="isLoading" @click="refreshAll"><AppIcon name="refresh" :size="16" />刷新</el-button>
      </div>
    </header>

    <section class="security-scan-filters finding-toolbar">
      <label>
        <span>报告任务</span>
        <el-select :model-value="selectedTaskId ?? ''" :disabled="!tasks.length" @change="selectTask(Number($event))">
          <el-option v-if="!tasks.length" value="" label="暂无任务" />
          <el-option v-for="task in tasks" :key="task.id" :value="task.id" :label="task.name" />
        </el-select>
      </label>
      <el-input v-model="keyword" clearable placeholder="搜索任务" @keyup.enter="loadTasks" />
      <el-select v-model="statusFilter" @change="loadTasks">
        <el-option value="" label="全部状态" />
        <el-option value="queued" label="排队中" />
        <el-option value="running" label="扫描中" />
        <el-option value="completed" label="已完成" />
        <el-option value="failed" label="失败" />
        <el-option value="canceled" label="已取消" />
      </el-select>
      <el-input v-model="findingKeyword" clearable placeholder="搜索风险 / CVE / 主机" @keyup.enter="reloadFindings" />
      <el-select v-model="severityFilter">
        <el-option value="" label="全部级别" />
        <el-option value="critical" label="严重" />
        <el-option value="high" label="高危" />
        <el-option value="medium" label="中危" />
        <el-option value="low" label="低危" />
        <el-option value="info" label="提示" />
      </el-select>
      <el-select v-model="categoryFilter">
        <el-option value="" label="全部分类" />
        <el-option value="baseline" label="基线" />
        <el-option value="port" label="端口" />
        <el-option value="cve" label="CVE" />
      </el-select>
      <el-select v-model="targetResultFilter">
        <el-option value="" label="全部主机" />
        <el-option v-for="target in targetResults" :key="target.id" :value="String(target.id)" :label="target.hostName" />
      </el-select>
      <el-button :loading="isLoadingFindings" :disabled="!selectedTask" @click="reloadFindings"><AppIcon name="search" :size="15" />筛选</el-button>
      <el-tag type="info" effect="plain">{{ taskOptionsLabel }} · 可扫描目标 {{ targets.length }} 台</el-tag>
    </section>

    <main class="security-report-pane">
      <template v-if="selectedTask">
        <header class="security-report-head">
          <div>
            <h3>{{ selectedTask.name }}</h3>
            <p>{{ selectedTask.createdBy }} · {{ selectedTask.targetCount }} 台目标 · 风险 {{ selectedTaskRiskTotal }} 项</p>
          </div>
          <div class="security-report-actions">
            <el-button v-if="canUsePageAction('securityScan', 'scan')" :disabled="!selectedTaskCanCancel || isControlBusy" @click="cancelSelectedTask">取消</el-button>
            <el-button v-if="canUsePageAction('securityScan', 'scan')" :disabled="!failedTargetsInSelectedTask || isControlBusy" @click="retryFailedTargets">重试失败</el-button>
            <el-button v-if="canUsePageAction('securityScan', 'export')" @click="exportTask('csv')"><AppIcon name="download" :size="15" />CSV</el-button>
            <el-button v-if="canUsePageAction('securityScan', 'export')" @click="exportTask('json')"><AppIcon name="download" :size="15" />JSON</el-button>
            <el-button v-if="canUsePageAction('securityScan', 'delete')" type="danger" plain @click="removeSelectedTask"><AppIcon name="trash" :size="15" />删除</el-button>
          </div>
        </header>

        <el-tabs v-model="activeReportTab" class="report-tabs">
          <el-tab-pane v-for="tab in reportTabs" :key="tab.key" :name="tab.key" :label="`${tab.label} ${tab.count}`" />
        </el-tabs>

        <section v-if="activeReportTab === 'overview'" class="security-report-section">
          <h3>综述</h3>
          <el-descriptions class="overview-table" :column="3" border>
            <el-descriptions-item label="报告名称" :span="2">{{ selectedTask.name }}</el-descriptions-item>
            <el-descriptions-item label="报告生成时间">{{ selectedTaskReportTime }}</el-descriptions-item>
            <el-descriptions-item label="用户名称">{{ selectedTask.createdBy }}</el-descriptions-item>
            <el-descriptions-item label="任务状态">
              <el-tag class="scan-status" :class="`status-${selectedTask.status}`" effect="plain">{{ statusLabel(selectedTask.status) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="扫描模块">{{ selectedTaskModulesText }}</el-descriptions-item>
            <el-descriptions-item label="目标资产">{{ selectedTask.targetCount }}</el-descriptions-item>
            <el-descriptions-item label="已完成">{{ selectedTask.completedCount }}</el-descriptions-item>
            <el-descriptions-item label="失败主机">{{ selectedTask.failedCount }}</el-descriptions-item>
            <el-descriptions-item label="风险总数">{{ selectedTaskRiskTotal }}</el-descriptions-item>
            <el-descriptions-item label="严重"><b class="severity-critical">{{ selectedTask.riskCounts.critical }}</b></el-descriptions-item>
            <el-descriptions-item label="高危"><b class="severity-high">{{ selectedTask.riskCounts.high }}</b></el-descriptions-item>
            <el-descriptions-item label="中危"><b class="severity-medium">{{ selectedTask.riskCounts.medium }}</b></el-descriptions-item>
            <el-descriptions-item label="低危"><b class="severity-low">{{ selectedTask.riskCounts.low }}</b></el-descriptions-item>
            <el-descriptions-item label="提示"><b class="severity-info">{{ selectedTask.riskCounts.info }}</b></el-descriptions-item>
            <el-descriptions-item label="漏洞源" :span="2">{{ sourceStatusText }}</el-descriptions-item>
            <el-descriptions-item label="全局运行中任务">{{ summary.taskCounts.running }}</el-descriptions-item>
          </el-descriptions>
        </section>

        <section v-else-if="activeReportTab === 'assets'" class="security-report-section">
          <h3>资产风险统计</h3>
          <el-table :data="assetRiskRows" class="asset-report-table app-data-table" row-key="id" empty-text="暂无资产风险统计">
            <el-table-column prop="index" label="序号" width="80" />
            <el-table-column prop="hostIp" label="IP/URL地址" min-width="150" />
            <el-table-column prop="hostName" label="资产名称" min-width="150" />
            <el-table-column prop="businessGroup" label="业务组" min-width="120" />
            <el-table-column prop="owner" label="责任人" min-width="120" />
            <el-table-column prop="coreAsset" label="是否核心" width="100" />
            <el-table-column prop="riskTotal" label="风险总数" width="100" />
            <el-table-column prop="riskType" label="风险类型" min-width="160" />
            <el-table-column prop="critical" label="严重" width="80" />
            <el-table-column prop="high" label="高危" width="80" />
            <el-table-column prop="medium" label="中危" width="80" />
            <el-table-column prop="low" label="低危" width="80" />
            <el-table-column prop="info" label="提示" width="80" />
          </el-table>
        </section>

        <section v-else-if="activeReportTab === 'impact'" class="security-report-section">
          <h3>漏洞影响统计</h3>
          <el-table :data="impactRows" class="impact-report-table app-data-table" row-key="key" empty-text="当前筛选条件下没有漏洞影响统计">
            <el-table-column prop="index" label="序号" width="80" />
            <el-table-column prop="title" label="漏洞名称" min-width="220" class-name="report-text-cell" />
            <el-table-column label="风险等级" width="110">
              <template #default="{ row }"><b :class="severityClass(row.severity)">{{ severityLabels[row.severity] }}</b></template>
            </el-table-column>
            <el-table-column prop="riskType" label="风险类型" min-width="140" />
            <el-table-column prop="affectedAssets" label="影响资产" min-width="180" class-name="report-text-cell" />
            <el-table-column prop="affectedAssetCount" label="影响资产数量" width="130" />
            <el-table-column prop="occurrences" label="出现次数" width="100" />
          </el-table>
        </section>

        <section v-else-if="activeReportTab === 'details'" class="security-report-section">
          <h3>漏洞详情</h3>
          <el-table :data="findings" class="finding-detail-table app-data-table" row-key="id" empty-text="当前筛选条件下没有漏洞详情">
            <el-table-column label="序号" width="80">
              <template #default="{ $index }">{{ $index + 1 }}</template>
            </el-table-column>
            <el-table-column label="风险等级" width="110">
              <template #default="{ row }"><b :class="severityClass(row.severity)">{{ severityLabels[row.severity] }}</b></template>
            </el-table-column>
            <el-table-column label="主机/域名" min-width="150">
              <template #default="{ row }">{{ row.targetIp || row.targetName }}</template>
            </el-table-column>
            <el-table-column label="风险端口" width="100">
              <template #default="{ row }">{{ row.port || '-' }}</template>
            </el-table-column>
            <el-table-column prop="title" label="漏洞名称" min-width="220" class-name="report-text-cell" />
            <el-table-column label="检测类型" min-width="140">
              <template #default="{ row }">{{ detectionType(row) }}</template>
            </el-table-column>
            <el-table-column label="漏洞类型" min-width="120">
              <template #default="{ row }">{{ categoryLabel(row.category) }}</template>
            </el-table-column>
            <el-table-column label="CVE编号" min-width="140">
              <template #default="{ row }">{{ row.cveId || '-' }}</template>
            </el-table-column>
            <el-table-column label="风险描述" min-width="220" class-name="report-text-cell">
              <template #default="{ row }">{{ findingDescription(row) }}</template>
            </el-table-column>
            <el-table-column label="风险影响" min-width="160" class-name="report-text-cell">
              <template #default="{ row }">{{ row.cwe || row.cvss || '-' }}</template>
            </el-table-column>
            <el-table-column label="解决方案" min-width="220" class-name="report-text-cell">
              <template #default="{ row }">{{ row.recommendation || '-' }}</template>
            </el-table-column>
            <el-table-column label="风险举证" min-width="220" class-name="report-text-cell">
              <template #default="{ row }">{{ findingEvidence(row) }}</template>
            </el-table-column>
          </el-table>
          <el-button v-if="findingsHasNext" class="finding-load-more" :loading="isLoadingFindings" @click="loadFindings()">
            <AppIcon name="chevronsRight" :size="16" />{{ isLoadingFindings ? '加载中...' : '加载更多' }}
          </el-button>
        </section>
      </template>
      <el-empty v-else class="security-empty" description="暂无扫描任务，请新建巡检后查看报告" />
    </main>

    <el-drawer v-model="isDrawerOpen" class="security-drawer security-popup-drawer" title="新建安全巡检" size="520px" :close-on-click-modal="false">
      <template #default>
        <div class="popup-body security-drawer-body">
          <p>扫描过程只执行只读命令，不会修改目标主机状态。</p>
          <div class="scan-form-grid popup-form-grid">
            <label>
              <span>任务名称</span>
              <el-input v-model="taskName" maxlength="180" placeholder="留空自动生成" />
            </label>
            <label>
              <span>端口范围</span>
              <el-input v-model="portsInput" type="textarea" :rows="3" />
            </label>
          </div>
          <div class="scan-module-options">
            <el-checkbox v-model="scanBaseline">基线检查</el-checkbox>
            <el-checkbox v-model="scanPorts">端口风险</el-checkbox>
            <el-checkbox v-model="scanCve" :disabled="!summary.vulnerabilitySource.onlineCveEnabled">CVE 检查</el-checkbox>
            <el-alert v-if="!summary.vulnerabilitySource.onlineCveEnabled" type="info" :closable="false" title="在线 CVE 默认关闭，可在系统设置中开启。" />
          </div>
          <div class="target-picker-head">
            <el-checkbox
              :model-value="filteredTargets.length > 0 && filteredTargets.every((target) => selectedTargetIds.has(target.id))"
              @change="toggleAllVisibleTargets(Boolean($event))"
            >
              全选当前列表
            </el-checkbox>
            <el-input v-model="targetKeyword" clearable placeholder="搜索主机 / IP / 分组" />
            <el-tag type="info" effect="plain">已选 {{ selectedTargets.length }} / {{ targets.length }}</el-tag>
          </div>
          <div class="target-picker-list">
            <el-checkbox
              v-for="target in filteredTargets"
              :key="target.id"
              :model-value="selectedTargetIds.has(target.id)"
              @change="toggleTarget(target.id, Boolean($event))"
            >
              <strong>{{ target.name }}</strong>
              <span>{{ target.privateIp }} · {{ target.os }} · {{ target.groupName }}</span>
            </el-checkbox>
            <el-empty v-if="!filteredTargets.length" class="security-empty" description="暂无可扫描 Linux SSH 主机" />
          </div>
        </div>
      </template>
      <template #footer>
        <div class="popup-actions">
          <el-button @click="isDrawerOpen = false">取消</el-button>
          <el-button type="primary" :disabled="!canStartScan" :loading="isCreating" @click="startScan">{{ isCreating ? '创建中...' : '开始扫描' }}</el-button>
        </div>
      </template>
    </el-drawer>
  </section>
</template>
