<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';

import { apiGet } from '../../api';
import { useAppContext } from '@app/context';
import { errorMessage } from '@shared/utils/errors';
import AppIcon from '@shared/components/AppIcon.vue';
import AppPagination from '@shared/components/AppPagination.vue';
import SystemSearchPanel from '@shared/components/SystemSearchPanel.vue';

type LoginLogStatus = 'success' | 'failed';
type StatusFilter = '' | LoginLogStatus;
type DateRange = [string, string] | null;
type ColumnKey = 'createdAt' | 'username' | 'status' | 'ipAddress' | 'userAgent' | 'message';

interface LoginLog {
  id: number;
  username: string;
  ipAddress: string | null;
  userAgent: string;
  status: LoginLogStatus;
  message: string;
  createdAt: string;
}

interface LoginLogPage {
  results: LoginLog[];
  total: number;
  page: number;
  pageSize: number;
}

interface ColumnOption {
  key: ColumnKey;
  label: string;
}

const columnOptions: readonly ColumnOption[] = [
  { key: 'createdAt', label: '时间' },
  { key: 'username', label: '账户名' },
  { key: 'status', label: '状态' },
  { key: 'ipAddress', label: '登录 IP' },
  { key: 'userAgent', label: 'User Agent' },
  { key: 'message', label: '提示信息' },
];

const { activeTool, canUsePageAction, canUseAnyPageAction } = useAppContext();

const logs = ref<LoginLog[]>([]);
const username = ref('');
const loginIp = ref('');
const statusFilter = ref<StatusFilter>('');
const dateRange = ref<DateRange>(null);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const isLoading = ref(false);
const message = ref('');
const columnsOpen = ref(false);
const fullscreen = ref(false);
const visibleColumns = ref<Record<ColumnKey, boolean>>({
  createdAt: true,
  username: true,
  status: true,
  ipAddress: true,
  userAgent: true,
  message: true,
});

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)));
const visibleColumnCount = computed(() => Object.values(visibleColumns.value).filter(Boolean).length);
const allColumnsVisible = computed(() => columnOptions.every((column) => visibleColumns.value[column.key]));
const someColumnsVisible = computed(() => visibleColumnCount.value > 0);

onMounted(loadLogs);

watch(pageSize, () => {
  page.value = 1;
  loadLogs();
});

async function loadLogs() {
  isLoading.value = true;
  message.value = '';
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      pageSize: String(pageSize.value),
    });
    const account = username.value.trim();
    const ip = loginIp.value.trim();
    if (account) params.set('username', account);
    if (ip) params.set('ip', ip);
    if (statusFilter.value) params.set('status', statusFilter.value);
    if (dateRange.value?.length === 2) {
      params.set('startTime', dateRange.value[0]);
      params.set('endTime', dateRange.value[1]);
    }

    const data = await apiGet<LoginLogPage>(`/api/system/login-logs/?${params.toString()}`);
    logs.value = data.results;
    total.value = data.total;
    if (data.page !== page.value) page.value = data.page;
    if (page.value > totalPages.value) setPage(totalPages.value);
  } catch (error) {
    logs.value = [];
    total.value = 0;
    message.value = errorMessage(error);
  } finally {
    isLoading.value = false;
  }
}

function searchLogs() {
  page.value = 1;
  loadLogs();
}

function resetSearch() {
  username.value = '';
  loginIp.value = '';
  statusFilter.value = '';
  dateRange.value = null;
  searchLogs();
}

function setPage(nextPage: number) {
  const normalized = Math.min(Math.max(1, nextPage), totalPages.value);
  if (normalized === page.value) return;
  page.value = normalized;
  loadLogs();
}

function setPageSize(nextPageSize: number) {
  pageSize.value = nextPageSize;
}

function isColumnVisible(key: ColumnKey) {
  return visibleColumns.value[key];
}

function toggleColumn(key: ColumnKey, eventOrChecked: Event | boolean | string | number) {
  const checked = typeof eventOrChecked === 'boolean' ? eventOrChecked : Boolean(eventOrChecked);
  if (!checked && visibleColumnCount.value <= 1) return;
  visibleColumns.value = { ...visibleColumns.value, [key]: checked };
}

function toggleAllColumns(eventOrChecked: Event | boolean | string | number) {
  const checked = typeof eventOrChecked === 'boolean' ? eventOrChecked : Boolean(eventOrChecked);
  if (!checked) return;
  visibleColumns.value = columnOptions.reduce(
    (columns, column) => ({ ...columns, [column.key]: true }),
    {} as Record<ColumnKey, boolean>,
  );
}

function resetColumns() {
  visibleColumns.value = columnOptions.reduce(
    (columns, column) => ({ ...columns, [column.key]: true }),
    {} as Record<ColumnKey, boolean>,
  );
}

function formatTime(value: string) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.replace('T', ' ').slice(0, 19);
  const pad = (number: number) => String(number).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function statusText(status: LoginLogStatus) {
  return status === 'success' ? '成功' : '失败';
}

function statusTagType(status: LoginLogStatus) {
  return status === 'success' ? 'success' : 'danger';
}
</script>

<template>
  <section v-if="activeTool === 'loginLogs'" class="login-log-page" :class="{ fullscreen }" @click="columnsOpen = false">
    <template v-if="canUseAnyPageAction('loginLogs', ['refresh', 'filter', 'columns'])">
      <SystemSearchPanel v-if="canUsePageAction('loginLogs', 'filter')">
        <el-form class="system-search-form" inline label-position="left" @submit.prevent="searchLogs">
          <el-form-item label="账户名称">
            <el-input v-model="username" class="system-search-field" placeholder="请输入用户名称" clearable @keyup.enter="searchLogs" />
          </el-form-item>
          <el-form-item label="IP 地址">
            <el-input v-model="loginIp" class="system-search-field" placeholder="请输入 IP 地址" clearable @keyup.enter="searchLogs" />
          </el-form-item>
          <el-form-item label="登录状态">
            <el-select v-model="statusFilter" class="system-search-field" placeholder="请选择日志状态" clearable>
              <el-option label="登录成功" value="success" />
              <el-option label="登录失败" value="failed" />
            </el-select>
          </el-form-item>
          <el-form-item label="访问时间" class="system-search-date-item">
            <el-date-picker
              v-model="dateRange"
              class="system-search-date-range"
              type="datetimerange"
              value-format="YYYY-MM-DD HH:mm:ss"
              start-placeholder="开始日期"
              range-separator="至"
              end-placeholder="结束日期"
              :default-time="[new Date(2000, 1, 1, 0, 0, 0), new Date(2000, 1, 1, 23, 59, 59)]"
            />
          </el-form-item>
          <el-form-item class="system-search-actions">
            <el-button type="primary" plain @click="searchLogs">
              <AppIcon name="search" :size="16" />
              搜索
            </el-button>
            <el-button type="danger" plain @click="resetSearch">
              <AppIcon name="reset" :size="16" />
              重置
            </el-button>
          </el-form-item>
        </el-form>
      </SystemSearchPanel>

      <article class="login-log-list-panel">
        <div class="login-log-toolbar">
          <h2>登录记录</h2>
          <div class="login-log-actions">
            <span v-if="canUseAnyPageAction('loginLogs', ['filter', 'refresh', 'columns'])" class="login-log-toolbar-divider"></span>
            <el-tooltip v-if="canUsePageAction('loginLogs', 'refresh')" content="刷新" placement="top">
              <el-button circle @click="loadLogs"><AppIcon name="refresh" :size="18" /></el-button>
            </el-tooltip>
            <el-popover
              v-if="canUsePageAction('loginLogs', 'columns')"
              v-model:visible="columnsOpen"
              placement="bottom-end"
              trigger="click"
              width="220"
              popper-class="login-log-column-menu"
              @click.stop
            >
              <template #reference>
                <el-button circle @click.stop><AppIcon name="settings" :size="18" /></el-button>
              </template>
              <div class="login-log-column-menu-head">
                <el-checkbox
                  :model-value="allColumnsVisible"
                  :indeterminate="someColumnsVisible && !allColumnsVisible"
                  @change="toggleAllColumns"
                >
                  列显示
                </el-checkbox>
                <el-button size="small" text type="primary" @click="resetColumns">重置</el-button>
              </div>
              <div class="login-log-column-options">
                <el-checkbox
                  v-for="column in columnOptions"
                  :key="column.key"
                  :model-value="isColumnVisible(column.key)"
                  :disabled="visibleColumnCount <= 1 && isColumnVisible(column.key)"
                  @change="toggleColumn(column.key, $event)"
                >
                  {{ column.label }}
                </el-checkbox>
              </div>
            </el-popover>
            <el-tooltip :content="fullscreen ? '退出全屏' : '全屏'" placement="top">
              <el-button circle @click="fullscreen = !fullscreen">
                <AppIcon :name="fullscreen ? 'minimize' : 'maximize'" :size="18" />
              </el-button>
            </el-tooltip>
          </div>
        </div>

        <p v-if="message" class="login-log-message">{{ message }}</p>

        <div class="login-log-table-wrap">
          <el-table :data="logs" row-key="id" class="login-log-table app-data-table" v-loading="isLoading" empty-text="暂无登录记录">
            <el-table-column v-if="isColumnVisible('createdAt')" label="时间" min-width="170">
              <template #default="{ row }">{{ formatTime(row.createdAt) }}</template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('username')" prop="username" label="账户名" min-width="120" show-overflow-tooltip />
            <el-table-column v-if="isColumnVisible('status')" label="状态" min-width="90">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small" effect="dark">{{ statusText(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('ipAddress')" label="登录 IP" min-width="150">
              <template #default="{ row }">{{ row.ipAddress || '-' }}</template>
            </el-table-column>
            <el-table-column v-if="isColumnVisible('userAgent')" prop="userAgent" label="User Agent" min-width="300" show-overflow-tooltip />
            <el-table-column v-if="isColumnVisible('message')" prop="message" label="提示信息" min-width="240" show-overflow-tooltip />
          </el-table>
        </div>

        <div class="host-pagination" aria-label="登录记录分页">
          <AppPagination
            :page="page"
            :page-size="pageSize"
            :total="total"
            @page-change="setPage"
            @page-size-change="setPageSize"
          />
        </div>
      </article>
    </template>
    <div v-else class="permission-empty">暂无可用功能</div>
  </section>
</template>
