import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

function readSource(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(`../${relativePath}`, import.meta.url)), 'utf8');
}

function readProjectFile(relativePath: string) {
  return readFileSync(fileURLToPath(new URL(`../../${relativePath}`, import.meta.url)), 'utf8');
}

describe('app shell upgrade contract', () => {
  it('wires Element Plus as the only UI component library', () => {
    const main = readSource('main.ts');
    const packageJson = readProjectFile('package.json');

    expect(packageJson).toContain('"element-plus"');
    expect(packageJson).not.toContain('"ant-design-vue"');
    expect(main).toContain("import 'element-plus/dist/index.css';");
    expect(main).toContain("import zhCn from 'element-plus/es/locale/lang/zh-cn';");
    expect(main).toContain('app.use(ElementPlus, { locale: zhCn })');
    expect(main).not.toContain('ant-design-vue');
    expect(main).not.toContain('app.use(Antd)');
  });

  it('renders the logged-in shell with Element Plus navigation and quick actions', () => {
    const app = readSource('App.vue');
    const styles = readSource('styles/base/workspace-header.css');
    const navStyles = readSource('styles/base/shell-nav.css');

    expect(app).toContain('<el-menu');
    expect(app).toContain('<el-sub-menu');
    expect(app).toContain('<el-breadcrumb');
    expect(app).toContain('<el-dropdown');
    expect(app).toContain('<el-tooltip');
    expect(app).toContain('<el-button');
    expect(app).not.toContain('<a-float-button');
    expect(navStyles).toContain('.el-menu');
    expect(navStyles).toContain('.workspace-float-actions');
  });

  it('includes a live date and time display at the bottom of the sidebar', () => {
    const app = readSource('App.vue');
    const navStyles = readSource('styles/base/shell-nav.css');

    expect(app).toContain('sidebar-clock');
    expect(app).toContain('sidebar-clock-date');
    expect(app).toContain('sidebar-clock-time');
    expect(app).toContain('onMounted');
    expect(app).toContain('onUnmounted');
    expect(navStyles).toContain('.sidebar-clock');
    expect(navStyles).toContain('flex-direction: column');
    expect(navStyles).toContain('.sidebar-nav');
  });

  it('uses larger bold typography for the sidebar navigation labels', () => {
    const navStyles = readSource('styles/base/shell-nav.css');
    const menuRule = navStyles.match(/\.workspace-nav-menu :is\(\.el-menu-item, \.el-sub-menu__title\) \{[\s\S]*?\n\}/)?.[0] ?? '';

    expect(menuRule).toContain('font-size: 16px');
    expect(menuRule).toContain('font-weight: 900');
    expect(menuRule).toContain('height: 42px');
    expect(menuRule).toContain('border-radius: 4px');
    expect(menuRule).toContain('margin: 7px 0');
  });

  it('keeps the 1Panel-style collapse control in the brand row and preserves shell sizing and colors', () => {
    const app = readSource('App.vue');
    const navStyles = readSource('styles/base/shell-nav.css');

    const brandStart = app.indexOf('<div class="sidebar-brand">');
    const brandEnd = app.indexOf('</div>', brandStart);
    const brand = app.slice(brandStart, brandEnd);
    expect(brand).toContain('sidebar-brand-toggle');
    expect(brand).toContain('@click="toggleSidebar"');
    expect(app).toContain(':collapse-transition="false"');
    expect(app).toContain('popper-class="workspace-nav-popper"');
    expect(app).not.toContain('class="workspace-menu-button"');

    expect(navStyles).toContain('grid-template-columns: clamp(190px, 12vw, 220px) minmax(0, 1fr)');
    expect(navStyles).toContain('grid-template-columns: 76px minmax(0, 1fr)');
    expect(navStyles).toContain('background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%)');
    expect(navStyles).toContain('background: linear-gradient(180deg, #111827 0%, #0f172a 100%)');

    const collapsedBrandRule = navStyles.match(/\.sidebar\.collapsed \.sidebar-brand \{[\s\S]*?\n\}/)?.[0] ?? '';
    const collapsedLogoRule = navStyles.match(/\.sidebar\.collapsed \.sidebar-brand img \{[\s\S]*?\n\}/)?.[0] ?? '';
    const collapsedToggleRule = navStyles.match(/\.sidebar\.collapsed \.sidebar-brand-toggle \{[\s\S]*?\n\}/)?.[0] ?? '';
    expect(collapsedBrandRule).toContain('overflow: visible');
    expect(collapsedLogoRule).toContain('object-fit: contain');
    expect(collapsedToggleRule).toContain('position: relative');
    expect(collapsedToggleRule).not.toContain('right: -');
  });

  it('uses the 1Panel fade-transform transition for internal page switching', () => {
    const app = readSource('App.vue');
    const workspaceStyles = readSource('styles/base/workspace-header.css');

    expect(app).toContain('<Transition name="fade-transform" mode="out-in" appear>');
    expect(app).toContain('class="workspace-tool-view"');
    expect(app).toContain(':key="activeTool"');
    expect(workspaceStyles).toContain('.fade-transform-enter-active');
    expect(workspaceStyles).toContain('transition: all 0.2s;');
    expect(workspaceStyles).toContain('transform: translateX(-30px);');
    expect(workspaceStyles).toContain('transform: translateX(30px);');
  });

  it('keeps an explicit selection frame on nested sidebar menu items', () => {
    const navStyles = readSource('styles/base/shell-nav.css');
    const nestedActiveRule = navStyles.match(/\.workspace-nav-menu \.el-sub-menu \.el-menu-item\.is-active \{[\s\S]*?\n\}/)?.[0] ?? '';
    const nestedActiveMarker = navStyles.match(/\.workspace-nav-menu \.el-sub-menu \.el-menu-item\.is-active::before \{[\s\S]*?\n\}/)?.[0] ?? '';

    expect(nestedActiveRule).toContain('background: #fff');
    expect(nestedActiveRule).toContain('inset 0 0 0 2px var(--ui-primary)');
    expect(nestedActiveMarker).toContain('background: var(--ui-primary)');
  });

  it('visually indents nested sidebar items with a guide rail', () => {
    const navStyles = readSource('styles/base/shell-nav.css');
    const nestedMenuRule = navStyles.match(/\.workspace-nav-menu \.el-sub-menu \.el-menu \{[\s\S]*?\n\}/)?.[0] ?? '';
    const nestedItemRule = navStyles.match(/\.workspace-nav-menu \.el-sub-menu \.el-menu-item \{[\s\S]*?\n\}/)?.[0] ?? '';

    expect(nestedMenuRule).toContain('margin-left: 18px');
    expect(nestedMenuRule).toContain('padding-left: 0');
    expect(nestedMenuRule).not.toContain('border-left');
    expect(nestedItemRule).toContain('padding-left: 12px !important');
  });
});
