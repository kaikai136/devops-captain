<script setup lang="ts">
import { useAppContext } from '@app/context';

const {
  pingContinuous,
  setPingPreset,
  pingHost,
  pingCount,
  pingTimeout,
  pingInterval,
  runPing,
  isPinging,
  stopPing,
  exportPingResults,
  pingMetrics,
  pingChart,
  pingDetails,
  clearPingResults,
  canUsePageAction,
} = useAppContext();
</script>

<template>
  <div class="machine-ping-column">
    <article class="panel ping-config">
      <div class="panel-title compact">
        <h2>Ping 测试</h2>
        <el-checkbox v-model="pingContinuous" class="check-line ping-check top-check">连续 Ping（直到手动停止）</el-checkbox>
      </div>
      <div class="ping-presets">
        <el-button @click="setPingPreset('223.5.5.5')">阿里 DNS</el-button>
        <el-button @click="setPingPreset('119.29.29.29')">腾讯 DNS</el-button>
        <el-button @click="setPingPreset('114.114.114.114')">114 DNS</el-button>
        <el-button @click="setPingPreset('8.8.8.8')">Google DNS</el-button>
        <el-button @click="setPingPreset('baidu.com')">百度</el-button>
      </div>
      <div class="ping-target-block">
        <label><span>目标主机</span><el-input v-model="pingHost" @keyup.enter="runPing" /></label>
        <label><span>次数</span><el-input-number v-model="pingCount" :min="1" :max="200" @keyup.enter="runPing" /></label>
        <label><span>超时 (ms)</span><el-input-number v-model="pingTimeout" :min="300" :max="30000" :step="100" @keyup.enter="runPing" /></label>
        <label><span>间隔 (ms)</span><el-input-number v-model="pingInterval" :min="100" :max="10000" :step="100" @keyup.enter="runPing" /></label>
      </div>
      <div class="ping-actions">
        <el-button v-if="canUsePageAction('ports', 'ping')" type="primary" :loading="isPinging" @click="runPing">
          {{ isPinging ? 'Ping 中' : '开始 Ping' }}
        </el-button>
        <el-button :disabled="!isPinging" @click="stopPing">停止</el-button>
        <el-button v-if="canUsePageAction('ports', 'export_ping')" :disabled="!pingDetails.length" @click="exportPingResults">导出</el-button>
      </div>
    </article>

    <article class="panel ping-results">
      <div class="panel-title">
        <h2>Ping 结果</h2>
      </div>
      <div class="ping-metrics">
        <article><strong class="green">{{ pingMetrics.success_count }}</strong><span>成功</span></article>
        <article><strong class="danger-text">{{ pingMetrics.failure_count }}</strong><span>失败</span></article>
        <article><strong class="orange">{{ pingMetrics.loss_rate }}%</strong><span>丢包率</span></article>
        <article><strong>{{ pingMetrics.average_response_time ?? '--' }}</strong><span>平均 (ms)</span></article>
        <article><strong class="green">{{ pingMetrics.min_response_time ?? '--' }}</strong><span>最小 (ms)</span></article>
        <article><strong class="danger-text">{{ pingMetrics.max_response_time ?? '--' }}</strong><span>最大 (ms)</span></article>
        <article><strong class="purple-text">{{ pingMetrics.jitter ?? '--' }}</strong><span>抖动 (ms)</span></article>
        <article><strong>{{ pingMetrics.total_count }}</strong><span>总计</span></article>
      </div>
      <section class="ping-chart-panel">
        <div class="ping-section-title">
          <h3>延迟波形图</h3>
          <div class="ping-legend">
            <span><i class="latency-dot"></i>延迟</span>
            <span><i class="average-dot"></i>平均</span>
            <span><i class="timeout-dot"></i>超时</span>
          </div>
        </div>
        <div class="ping-chart">
          <svg v-if="pingDetails.length" :viewBox="`0 0 ${pingChart.width} ${pingChart.height}`" role="img" aria-label="Ping 延迟波形图">
            <g class="chart-grid">
              <g v-for="tick in pingChart.yTicks" :key="tick.value">
                <text :x="pingChart.padding.left - 10" :y="tick.y + 4" text-anchor="end">{{ tick.value }}</text>
                <line :x1="pingChart.padding.left" :x2="pingChart.width - pingChart.padding.right" :y1="tick.y" :y2="tick.y" />
              </g>
            </g>
            <line
              v-if="pingChart.averageY !== null"
              :x1="pingChart.padding.left"
              :x2="pingChart.width - pingChart.padding.right"
              :y1="pingChart.averageY"
              :y2="pingChart.averageY"
              class="average-line"
            />
            <path :d="pingChart.latencyPath" class="latency-line" />
            <circle
              v-for="point in pingChart.points"
              :key="point.item.sequence"
              :cx="point.x"
              :cy="point.y"
              r="4"
              :class="point.item.status === 'timeout' ? 'timeout-point' : 'latency-point'"
            />
            <g class="chart-x-axis">
              <text
                v-for="point in pingChart.points"
                :key="`label-${point.item.sequence}`"
                :x="point.x"
                :y="pingChart.height - 10"
                text-anchor="middle"
              >
                #{{ point.item.sequence }}
              </text>
            </g>
          </svg>
          <el-empty v-else class="ping-empty chart-empty" description="开始测试后，这里会展示延迟波形。" />
        </div>
      </section>
      <section class="ping-detail-box">
        <div class="ping-section-title">
          <h3>详细结果</h3>
          <el-button :disabled="!pingDetails.length || isPinging" @click="clearPingResults">清空</el-button>
        </div>
        <el-table :data="pingDetails" row-key="sequence" class="ping-detail-list app-data-table" empty-text="还没有测试结果。">
          <el-table-column label="#" width="80">
            <template #default="{ row }">#{{ row.sequence }}</template>
          </el-table-column>
          <el-table-column prop="ip" label="IP" min-width="150" />
          <el-table-column label="状态" min-width="100">
            <template #default="{ row }">
              <el-tag :type="row.status === 'online' ? 'success' : 'danger'" size="small" effect="dark">
                {{ row.status === 'online' ? '成功' : '超时' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="响应时间" min-width="120">
            <template #default="{ row }">{{ row.response_time ?? '--' }} ms</template>
          </el-table-column>
        </el-table>
      </section>
    </article>
  </div>
</template>
