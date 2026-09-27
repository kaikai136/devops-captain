import type { ToolKey } from '../types';

type NavGroupKey = 'network' | 'host' | 'market' | 'company' | 'security' | 'system';

export interface NavItem {
  key: ToolKey;
  label: string;
  desc: string;
}

export interface NavGroup {
  key: NavGroupKey;
  label: string;
  items: NavItem[];
}

export const dashboardNavItem: NavItem = {
  key: 'dashboard',
  label: '仪表盘',
  desc: '系统总览、资产统计与出口网络',
};

export const navGroups: NavGroup[] = [
  {
    key: 'host' as const,
    label: '资产管理',
    items: [
      { key: 'hosts' as const, label: '主机管理', desc: '分组资产、验证状态与终端入口' },
      { key: 'databaseManagement' as const, label: '应用管理', desc: '数据库资产、表结构与数据展示' },
      { key: 'sessionAudits' as const, label: '会话审计', desc: 'Web 终端命令审计与操作录像' },
      { key: 'bulkExecution' as const, label: '批量执行', desc: '对已验证 Linux SSH 主机并发执行命令' },
      { key: 'accounts' as const, label: '账号管理', desc: '用户账号、状态与权限管理' },
    ],
  },
  {
    key: 'market' as const,
    label: '应用市场',
    items: [
      { key: 'applicationMarket' as const, label: '应用市场', desc: 'Docker 应用目录、目标主机安装和后台任务' },
    ],
  },
  {
    key: 'company' as const,
    label: '设备管理',
    items: [
      { key: 'companyDevices' as const, label: '设备资产', desc: '公司设备资产、标签与使用信息管理' },
    ],
  },
  {
    key: 'network' as const,
    label: '网络工具',
    items: [
      { key: 'ip' as const, label: 'IP 探活', desc: '1-254 主机在线探测' },
      { key: 'ports' as const, label: '机器探测', desc: 'Ping 连通性与端口扫描' },
      { key: 'subnet' as const, label: 'IPv4 子网划分', desc: 'CIDR 计算与子网拆分' },
    ],
  },
  {
    key: 'security' as const,
    label: '安全工具',
    items: [
      { key: 'auth' as const, label: '双因子认证', desc: 'TOTP 动态口令' },
      { key: 'password' as const, label: '密码生成器', desc: '强密码生成与记录' },
      { key: 'securityScan' as const, label: '安全扫描', desc: 'Linux 主机基线、端口风险与 CVE 扫描' },
    ],
  },
  {
    key: 'system' as const,
    label: '系统管理',
    items: [
      { key: 'loginLogs' as const, label: '登录日志', desc: '查看用户登录时间、来源与状态' },
      { key: 'operationLogs' as const, label: '操作日志', desc: '查看系统用户操作记录信息' },
      { key: 'users' as const, label: '用户管理', desc: '维护系统用户与账号状态' },
      { key: 'roles' as const, label: '角色管理', desc: '配置角色权限与授权范围' },
      { key: 'profile' as const, label: '个人中心', desc: '头像资料、密码与登录保护' },
      { key: 'systemSettings' as const, label: '系统设置', desc: '管理系统基础参数与偏好' },
    ],
  },
];
