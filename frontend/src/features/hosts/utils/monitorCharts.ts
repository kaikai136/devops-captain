import type { MonitorPoint } from '../composables/useHostMonitor';

export function gaugeOption(value: number | null, color: string, dark: boolean, reduceMotion: boolean) {
  const foreground = dark ? '#e2e8f0' : '#243247';
  return {
    backgroundColor: 'transparent', animation: !reduceMotion, animationDurationUpdate: 600,
    series: [{
      type: 'gauge', startAngle: 210, endAngle: -30, min: 0, max: 100,
      center: ['50%', '57%'], radius: '94%', splitNumber: 5,
      progress: { show: true, width: 13, roundCap: true, itemStyle: { color } },
      axisLine: { roundCap: true, lineStyle: { width: 13, color: [[1, dark ? '#293646' : '#edf1f6']] } },
      axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false },
      pointer: { show: false }, anchor: { show: false }, title: { show: false },
      detail: { valueAnimation: !reduceMotion, offsetCenter: [0, '5%'], color: foreground, fontSize: 30, fontWeight: 700, formatter: value === null ? '--' : '{value}%' },
      data: [{ value: value === null ? 0 : Math.round(Math.min(100, Math.max(0, value)) * 10) / 10 }],
    }],
  };
}

export function trendOption(points: MonitorPoint[], network: boolean, dark: boolean, reduceMotion: boolean) {
  const colors = network ? ['#14b8a6', '#5b8ff9'] : ['#5b8ff9', '#14b8a6', '#a78bfa'];
  const names = network ? ['下行', '上行'] : ['CPU', '内存', '系统磁盘'];
  const fields: Array<keyof MonitorPoint> = network ? ['rx', 'tx'] : ['cpu', 'memory', 'disk'];
  const text = dark ? '#a7b4c6' : '#7a8799';
  return {
    backgroundColor: 'transparent', animation: !reduceMotion, animationDurationUpdate: 600, color: colors,
    tooltip: { trigger: 'axis', confine: true, backgroundColor: dark ? '#192333' : '#fff', textStyle: { color: dark ? '#e2e8f0' : '#243247' } },
    legend: { top: 0, right: 0, icon: 'circle', itemWidth: 8, itemHeight: 8, textStyle: { color: text } },
    grid: { left: 8, right: 20, top: 45, bottom: 10, containLabel: true },
    xAxis: {
      type: 'category', boundaryGap: false,
      data: points.map((point) => new Date(point.time).toLocaleTimeString('zh-CN', { hour12: false })),
      axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: text, hideOverlap: true },
    },
    yAxis: {
      type: 'value', min: 0, max: network ? undefined : 100,
      axisLabel: { color: text, formatter: network ? '{value} KiB/s' : '{value}%' },
      splitLine: { lineStyle: { color: dark ? '#293646' : '#e9eef4', type: 'dashed' } },
    },
    series: fields.map((field, index) => ({
      name: names[index], type: 'line', smooth: 0.3, showSymbol: points.length === 1,
      symbolSize: 5, connectNulls: false, lineStyle: { width: 2 },
      areaStyle: { opacity: 0.07 },
      data: points.map((point) => point[field] === null ? null : network ? Math.round(Number(point[field]) / 1024 * 100) / 100 : point[field]),
    })),
  };
}
