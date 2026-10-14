import { describe, expect, it } from 'vitest';
import { createSSRApp, h } from 'vue';
import { renderToString } from 'vue/server-renderer';

import { dashboardNavItem, navGroups } from '../app/navigation';
import { navGroupIcons, navItemIcons } from '../app/sidebarIcons';
import SidebarIcon from '../shared/components/SidebarIcon.vue';

describe('sidebar icon registry', () => {
  it('provides an icon for every current navigation key', () => {
    const itemKeys = [dashboardNavItem.key, ...navGroups.flatMap((group) => group.items.map((item) => item.key))];
    expect(Object.keys(navItemIcons).sort()).toEqual([...itemKeys].sort());
    expect(Object.keys(navGroupIcons).sort()).toEqual(navGroups.map((group) => group.key).sort());
    expect(Object.values(navItemIcons).every(Boolean)).toBe(true);
    expect(Object.values(navGroupIcons).every(Boolean)).toBe(true);
  });

  it('uses different visual concepts for unrelated sections', () => {
    expect(navItemIcons.hosts).not.toBe(navItemIcons.databaseManagement);
    expect(navItemIcons.hosts).not.toBe(navItemIcons.applicationMarket);
    expect(navItemIcons.sessionAudits).not.toBe(navItemIcons.securityScan);
    expect(navGroupIcons.security).not.toBe(navGroupIcons.system);
    expect(navGroupIcons.host).not.toBe(navItemIcons.hosts);
    expect(navGroupIcons.company).not.toBe(navItemIcons.companyDevices);
  });

  it('renders every navigation icon as an accessible, self-contained SVG', async () => {
    for (const name of new Set([...Object.values(navItemIcons), ...Object.values(navGroupIcons)])) {
      const app = createSSRApp({ render: () => h(SidebarIcon, { name, size: 20 }) });
      const markup = await renderToString(app);
      expect(markup, name).toContain('<svg');
      expect(markup, name).toContain('aria-hidden="true"');
    }
  });
});
