import type { ToolKey } from '../types';
import type { NavGroup } from './navigation';
import type { SidebarIconName } from '@shared/components/SidebarIcon.vue';

// Keep navigation semantics and icon choices in one exhaustively typed map.
export const navItemIcons = {
  dashboard: 'dashboard',
  hosts: 'hosts',
  databaseManagement: 'databaseManagement',
  sessionAudits: 'sessionAudits',
  bulkExecution: 'bulkExecution',
  accounts: 'accounts',
  applicationMarket: 'applicationMarket',
  applicationKeys: 'applicationKeys',
  companyDevices: 'companyDevices',
  ip: 'ip',
  ports: 'ports',
  subnet: 'subnet',
  auth: 'auth',
  password: 'password',
  securityScan: 'securityScan',
  loginLogs: 'loginLogs',
  operationLogs: 'operationLogs',
  users: 'users',
  roles: 'roles',
  profile: 'profile',
  systemSettings: 'systemSettings',
} as const satisfies Record<ToolKey, SidebarIconName>;

export const navGroupIcons = {
  host: 'assetGroup',
  market: 'marketGroup',
  company: 'deviceGroup',
  network: 'networkGroup',
  security: 'securityGroup',
  system: 'systemGroup',
} as const satisfies Record<NavGroup['key'], SidebarIconName>;
