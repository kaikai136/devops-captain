import { describe, expect, it } from 'vitest';
import { init, use } from 'echarts/core';
import { GaugeChart } from 'echarts/charts';
import { SVGRenderer } from 'echarts/renderers';
import { gaugeOption } from '../monitorCharts';

use([GaugeChart, SVGRenderer]);

describe('monitor gauge rendering', () => {
  it('renders missing, sampled, updated and missing values without breaking ECharts progress state', () => {
    const chart = init(null, null, { renderer: 'svg', ssr: true, width: 300, height: 150 });
    try {
      for (const value of [null, 42, 75, 0, null, 30]) {
        const option = gaugeOption(value, '#5b8ff9', false, true);
        expect(option.series[0].progress.show).toBe(true);
        expect(() => chart.setOption(option, { notMerge: true })).not.toThrow();
        expect(chart.renderToSVGString()).toContain(value === null ? '--' : `${value}%`);
      }
    } finally {
      chart.dispose();
    }
  });
});
