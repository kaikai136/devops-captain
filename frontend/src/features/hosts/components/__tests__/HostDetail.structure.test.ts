import { readFileSync } from 'node:fs';
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc';
import { describe, expect, it } from 'vitest';
import { appendContainerToSocketUrl } from '../../api/monitoring';
import { gaugeOption, trendOption } from '../../utils/monitorCharts';

const source = readFileSync(new URL('../HostDetail.vue', import.meta.url), 'utf8');
const manager = readFileSync(new URL('../HostManager.vue', import.meta.url), 'utf8');
const table = readFileSync(new URL('../HostTable.vue', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../../../styles/tools/host/detail.css', import.meta.url), 'utf8');

describe('host detail UI contract', () => {
  it('matches Docker image and network screenshot columns', () => {
    const images = source.slice(source.indexOf(`<el-table v-if="docker.activeTab === 'images'"`), source.indexOf(`<el-table v-if="docker.activeTab === 'networks'"`));
    const networks = source.slice(source.indexOf(`<el-table v-if="docker.activeTab === 'networks'"`), source.indexOf(`<el-table v-if="docker.activeTab === 'volumes'"`));
    expect(images).toContain('v-for="column in visibleImageColumns"');
    expect(images).toContain(':label="column.label"');
    expect([...networks.matchAll(/label="([^"]+)"/g)].map((match) => match[1])).toEqual(['NETWORK ID', 'NAME', 'DRIVER', 'SCOPE']);
    expect(images).toContain('v-for="reference in imageReferences(row)"');
    expect(images).toContain(':title="reference"');
    expect(images).not.toContain('repositories.join');
    for (const table of [images, networks]) {
      expect(table).toContain(':title="row.id"');
      expect(table).toContain('shortDockerId(row.id)');
    }
    expect(images).toContain('dockerField(imageValue(row, column.key))');
    expect(css).toContain('.host-docker-references { display: flex; flex-direction: column;');
  });
  it('switches resource views inside a fixed viewport through accessible icon buttons', () => {
    expect(source).toContain('@click="toggleMetric(gauge.icon)"');
    expect(source).toContain(':aria-pressed="detailMetrics.has(gauge.icon)"');
    expect(source).not.toContain('aria-expanded');
    expect(source).toContain('<template v-if="!detailMetrics.has(gauge.icon)"');
    expect(source).toContain('</div></div><p>{{ gauge.footer }}</p>');
    expect(css).toContain('.host-metric-viewport { height: 150px; min-height: 150px;');
    expect(css).toContain('height: 100%; min-width: 0; overflow-y: auto;');
    expect(css).not.toContain('max-height: 260px');
    expect(source).toContain('snapshot?.cpu.perCore ?? []');
    expect(source).toContain('host-cpu-loads');
    expect(source).toContain('memoryDetails');
    expect(css).toContain('.host-metric-toggle:focus-visible');
  });
  it('compiles Element Plus cards, tables, logs and existing chart component', () => {
    const { descriptor, errors } = parse(source);
    expect(errors).toEqual([]);
    const script = compileScript(descriptor, { id: 'host-detail' });
    expect(compileTemplate({ source: descriptor.template!.content, filename: 'HostDetail.vue', id: 'host-detail', compilerOptions: { bindingMetadata: script.bindings } }).errors).toEqual([]);
    for (const component of ['el-card', 'el-table', 'el-dialog', 'el-alert', 'DashboardChart']) expect(source).toContain(`<${component}`);
    expect(source).toContain('ElMessageBox.confirm');
    expect(source).toContain('refreshIntervals = [10, 15, 20]');
    expect(source).toContain('aria-label="监控刷新间隔"');
    expect(source).toContain('每 ${refreshIntervalSeconds} 秒自动刷新');
    expect(source).not.toContain(':loading="loading"');
    expect(source).not.toContain('返回主机列表');
    expect(source).not.toContain('v-loading');
    expect(source).toContain('时间颗粒度');
    expect(source).toContain('docker.loading[docker.activeTab] && !dockerData');
    expect(source).toContain('aria-current');
    expect(source).toContain('docker.select(tab.key)');
    expect(source).toContain("'images'");
    expect(source).toContain('最近 15 分钟');
  });

  it('keeps the list mounted and offers permission-gated public/private IP entrypoints', () => {
    expect(manager).toContain('v-show="!selectedDetail"');
    expect(manager).toContain('@open-detail="openHostDetail"');
    expect(manager).toContain('v-for="host in detailHosts" v-show="detailHostId === host.id" :key="host.id"');
    expect(manager).not.toContain('v-if="selectedDetail');
    const app = readFileSync(new URL('../../../../App.vue', import.meta.url), 'utf8');
    expect(app).toContain('<HostManager v-if="hostManagerOpened" v-show="activeTool === \'hosts\'" />');
    expect(app).not.toContain('<HostManager v-else-if=');
    expect(manager).toContain('host-workspace-tabs');
    expect(table).toContain('host.publicIp && props.canOpenTerminal');
    expect(table).toContain('查看主机 ${host.name} IP ${host.privateIp} 的监控');
    expect(table).toContain('<span v-else>{{ host.privateIp }}</span>');
  });

  it('opens the system information terminal through the personal terminal popup', () => {
    expect(manager).toContain('@terminal="openSimpleHostTerminal"');
    expect(manager).not.toContain('@terminal="openWebTerminal"');
  });

  it('handles theme, unknown gauges, responsiveness and reduced motion', () => {
    const gauge = gaugeOption(null, '#5b8ff9', true, true);
    expect(gauge.animation).toBe(false);
    expect(gauge.series[0].detail.formatter).toBe('--');
    expect(gauge.backgroundColor).toBe('transparent');
    expect(trendOption([], false, false, true).series).toHaveLength(3);
    expect(trendOption([], true, true, false).series).toHaveLength(2);
    expect(css).toContain('var(--ui-card)');
    expect(css).toContain('max-width: 600px');
    expect(css).toContain('prefers-reduced-motion: reduce');
    expect(source).toContain('v-if="active"');
  });

  it('caches gauge options instead of rebuilding them for unrelated page state', () => {
    expect(source).toContain('const gaugeCards = computed(');
    expect(source).toContain(':option="gauge.option"');
    const chart = readFileSync(new URL('../../../../components/tools/dashboard/DashboardChart.vue', import.meta.url), 'utf8');
    expect(chart).not.toContain('deep: true');
    expect(chart).toContain('lazyUpdate: true');
  });

  it('sends container identifiers only to the requested host websocket', () => {
    expect(appendContainerToSocketUrl('ws://local/7/', 7, '?host=7&container=web')).toBe('ws://local/7/?container=web');
    expect(appendContainerToSocketUrl('ws://local/8/', 8, '?host=7&container=web')).toBe('ws://local/8/');
    expect(appendContainerToSocketUrl('ws://local/7/?x=1', 7, '?host=7&container=a%3Bb')).toBe('ws://local/7/?x=1&container=a%3Bb');
  });
});
