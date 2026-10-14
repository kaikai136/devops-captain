<script setup lang="ts">
import { computed } from 'vue';
import {
  RiAccountCircleLine,
  RiAppStoreLine,
  RiApps2Line,
  RiComputerLine,
  RiDashboardLine,
  RiDatabase2Line,
  RiFileList3Line,
  RiGitBranchLine,
  RiGroupLine,
  RiIdCardLine,
  RiLoginBoxLine,
  RiLockPasswordLine,
  RiMacbookLine,
  RiRadarLine,
  RiRouterLine,
  RiScan2Line,
  RiServerLine,
  RiSettings3Line,
  RiSettingsLine,
  RiShieldCheckLine,
  RiShieldKeyholeLine,
  RiShieldLine,
  RiStackLine,
  RiTerminalBoxLine,
  RiUserSettingsLine,
  RiVideoLine,
} from 'vue-icons-plus/ri';

// Remix Icon comes from the same collection listed by React Icons.
// Use its Vue components rather than installing React-only react-icons.
const icons = {
  dashboard: RiDashboardLine,
  assetGroup: RiStackLine,
  marketGroup: RiApps2Line,
  deviceGroup: RiComputerLine,
  networkGroup: RiRouterLine,
  securityGroup: RiShieldLine,
  systemGroup: RiSettingsLine,
  hosts: RiServerLine,
  databaseManagement: RiDatabase2Line,
  sessionAudits: RiVideoLine,
  bulkExecution: RiTerminalBoxLine,
  accounts: RiIdCardLine,
  applicationMarket: RiAppStoreLine,
  companyDevices: RiMacbookLine,
  ip: RiRadarLine,
  ports: RiScan2Line,
  subnet: RiGitBranchLine,
  auth: RiShieldKeyholeLine,
  password: RiLockPasswordLine,
  securityScan: RiShieldCheckLine,
  loginLogs: RiLoginBoxLine,
  operationLogs: RiFileList3Line,
  users: RiGroupLine,
  roles: RiUserSettingsLine,
  profile: RiAccountCircleLine,
  systemSettings: RiSettings3Line,
} as const;

export type SidebarIconName = keyof typeof icons;

const props = withDefaults(defineProps<{ name: SidebarIconName; size?: number }>(), {
  size: 20,
});

const iconComponent = computed(() => icons[props.name]);
</script>

<template>
  <component
    :is="iconComponent"
    class="sidebar-menu-icon"
    :size="size"
    aria-hidden="true"
    focusable="false"
  />
</template>
