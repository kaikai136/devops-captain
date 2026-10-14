# 侧边栏图标重构（基于 upstream/Element_update）

## 现状与问题

旧实现由 `useShellState.ts` 将菜单键映射到通用 `AppIcon`（Lucide）名称，
存在多个易混淆的复用：

- 主机管理、数据库应用管理、应用市场都用了服务器图标；
- 安全扫描和会话审计都用了扫描图标；
- 用户管理和个人中心都用了用户图标；
- 安全工具分组使用设置图标，系统管理分组使用仪表盘图标；
- 网络工具、设备管理等分组使用的设备/显示器图标过于相似。

## 依赖和选型

参考 [React Icons](https://react-icons.github.io/react-icons/) 收录的
[Remix Icon](https://remixicon.com/) 线性图标集。

本项目是 Vue 3，React-only 的 `react-icons` 组件不能直接渲染。
因此使用其 Vue 生态兼容方案 `vue-icons-plus/ri`，按名称导入 Remix Icon
SVG 组件，避免引入 React 运行时或使用在线图标 API。
只改变主侧边栏图标，其他页面继续使用现有 `@lucide/vue` 和 `AppIcon`。

## 选型表

| 位置 | Remix Icon | 设计意图 |
| --- | --- | --- |
| 仪表盘 | `RiDashboardLine` | 系统总览 |
| 资产管理分组 | `RiStackLine` | 资产集合 |
| 应用市场分组 | `RiApps2Line` | 应用分类 |
| 设备管理分组 | `RiComputerLine` | 公司终端设备 |
| 网络工具分组 | `RiRouterLine` | 网络连接 |
| 安全工具分组 | `RiShieldLine` | 安全防护 |
| 系统管理分组 | `RiSettingsLine` | 平台配置管理 |
| 主机管理 | `RiServerLine` | SSH 主机 |
| 应用管理（数据库） | `RiDatabase2Line` | 数据库资产 |
| 会话审计 | `RiVideoLine` | 会话录像 |
| 批量执行 | `RiTerminalBoxLine` | 命令执行 |
| 账号管理 | `RiIdCardLine` | 凭据与账号 |
| 应用市场 | `RiAppStoreLine` | 安装/管理应用 |
| 设备资产 | `RiMacbookLine` | 设备登记 |
| IP 探活 | `RiRadarLine` | 地址探测 |
| 机器探测 | `RiScan2Line` | 网络扫描 |
| 子网划分 | `RiGitBranchLine` | 分支/网络划分 |
| 双因子认证 | `RiShieldKeyholeLine` | 认证保护 |
| 密码生成器 | `RiLockPasswordLine` | 密码管理 |
| 安全扫描 | `RiShieldCheckLine` | 安全检查 |
| 登录日志 | `RiLoginBoxLine` | 登录事件 |
| 操作日志 | `RiFileList3Line` | 操作记录 |
| 用户管理 | `RiGroupLine` | 用户集合 |
| 角色管理 | `RiUserSettingsLine` | 授权配置 |
| 个人中心 | `RiAccountCircleLine` | 个人账户 |
| 系统设置 | `RiSettings3Line` | 具体系统参数 |

## 约束与验证

- 统一使用 20px 线性 SVG、继承菜单颜色，不修改 Element Plus 原生菜单行为。
- 图标仅作装饰，设置 `aria-hidden="true"`，菜单文字承载可访问名称。
- `app/sidebarIcons.ts` 通过 `satisfies Record<...>` 覆盖菜单键，新增菜单若不配置图标将触发类型报错。
- 回归测试验证完整性、关键语义区分，以及每个图标均可 SSR 输出 SVG。
- 不改动后端、权限、页面路由及 SFTP 功能。
