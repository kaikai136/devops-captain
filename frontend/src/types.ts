export type ToolKey =
  | 'dashboard'
  | 'ip'
  | 'hosts'
  | 'sessionAudits'
  | 'bulkExecution'
  | 'applicationMarket'
  | 'accounts'
  | 'companyDevices'
  | 'ports'
  | 'subnet'
  | 'auth'
  | 'password'
  | 'securityScan'
  | 'loginLogs'
  | 'operationLogs'
  | 'users'
  | 'roles'
  | 'profile'
  | 'systemSettings';

export interface HostResult {
  host: number;
  ip: string;
  status: 'online' | 'offline' | 'untested';
  response_time: number | null;
}

export interface IpScanResponse {
  results: HostResult[];
  total_hosts: number;
  active_hosts: number;
  duration: number;
  timeout_ms?: number;
  retries?: number;
  concurrency?: number;
}

export interface HostGroup {
  key: number;
  label: string;
  count: number;
  children?: HostGroup[];
}

export interface ManagedHost {
  id: number;
  name: string;
  group: number;
  publicIp?: string;
  privateIp: string;
  port: number;
  loginUser: string;
  loginPassword: string;
  privateKeyName: string;
  privateKey: string;
  machineName: string;
  systemArch: string;
  systemType: string;
  remark: string;
  cpu: number;
  memory: number;
  disk?: string;
  os: 'ubuntu' | 'centos' | 'debian' | 'windows';
  verified: boolean;
  verifyStatus?: 'unverified' | 'verified' | 'failed';
  createdAt?: string | null;
  updatedAt?: string | null;
  creator?: string;
  platformType?: 'linux' | 'windows' | string;
}

export interface HostCredential {
  id: number;
  name: string;
  username: string;
  password: string;
  port: number;
  privateKeyName: string;
  privateKey: string;
  remark: string;
}

export interface AccountUser {
  id: number;
  username: string;
  email: string;
  first_name: string;
  displayName?: string;
  avatarUrl?: string;
  twoFactorEnabled?: boolean;
  twoFactorRequired?: boolean;
  twoFactorResetRequired?: boolean;
  twoFactorStatus?: TwoFactorStatus;
  is_active: boolean;
  is_staff: boolean;
  is_superuser: boolean;
  featurePermissionCodes: string[];
  last_login: string | null;
  date_joined: string | null;
}

export interface LoginPayload {
  account: string;
  password: string;
  remember: boolean;
  sliderToken: string;
}

export interface LoginTwoFactorChallenge {
  twoFactorRequired: true;
  challengeId: string;
  account: string;
  displayName: string;
  expiresIn: number;
}

export type TwoFactorStatus = 'disabled' | 'required' | 'enabled';

export interface LoginTwoFactorSetupChallenge extends TwoFactorSetupPayload {
  twoFactorSetupRequired: true;
  challengeId: string;
  account: string;
  displayName: string;
  expiresIn: number;
}

export type LoginResult = { user: AccountUser } | LoginTwoFactorChallenge | LoginTwoFactorSetupChallenge;

export interface ProfilePayload {
  user: AccountUser;
  profile: {
    avatarUrl: string;
    twoFactorEnabled: boolean;
    twoFactorRequired: boolean;
    twoFactorResetRequired: boolean;
    twoFactorStatus: TwoFactorStatus;
    twoFactorConfirmedAt: string | null;
    updatedAt: string | null;
  };
}

export interface TwoFactorSetupPayload {
  secret: string;
  provisioningUri: string;
  qrDataUrl: string;
}

export interface PortScanResult {
  host: string;
  open_ports: number[];
  open_details?: Array<{ port: number; duration: number; service: string }>;
  scanned_ports: number;
  total_ports?: number;
  timeout_ms?: number;
  concurrency?: number;
  duration: number;
  error?: string;
}

export interface PingDetail {
  sequence: number;
  target: string;
  ip: string;
  status: 'online' | 'timeout';
  response_time: number | null;
  timestamp?: number;
}

export interface PingSession {
  details: PingDetail[];
  metrics: {
    success_count: number;
    failure_count: number;
    loss_rate: number;
    average_response_time: number | null;
    min_response_time: number | null;
    max_response_time: number | null;
    jitter: number | null;
    total_count: number;
  };
}

export interface SubnetResult {
  normalized_input: string;
  ip: string;
  prefix: number;
  mask: string;
  network: string;
  broadcast: string;
  first_host: string;
  last_host: string;
  usable_host_count: number;
  address_count: number;
  is_private?: boolean;
  is_loopback?: boolean;
  is_multicast?: boolean;
  binary: { ip: string; mask: string; network: string; broadcast: string };
  subnets?: Array<{
    index: number;
    cidr: string;
    network: string;
    first_host: string;
    last_host: string;
    gateway: string;
    broadcast: string;
    usable_host_count: number;
  }>;
}

export interface PasswordRecord {
  id: number;
  project_name: string;
  password: string;
  length: number;
  include_uppercase: boolean;
  include_lowercase: boolean;
  include_numbers: boolean;
  include_symbols: boolean;
  created_at: string;
}

export interface PasswordImportRecord {
  project_name: string;
  password: string;
  length: number;
  include_uppercase: boolean;
  include_lowercase: boolean;
  include_numbers: boolean;
  include_symbols: boolean;
}

export interface AuthEntry {
  id: number;
  issuer: string;
  account_name: string;
  secret: string;
  digits: number;
  period: number;
  algorithm: string;
  created_at: string;
  totp?: { code: string; remaining_seconds: number; period: number };
}

export interface QrPreview {
  dataUrl: string;
  uri: string;
  issuer: string;
  account: string;
}

export interface SystemSetting {
  id: number;
  key: string;
  label: string;
  description: string;
  value: unknown;
  updatedAt: string;
}

export interface WatermarkConfig {
  enabled: boolean;
  text: string;
  pages: string[];
}

export interface LogRetentionConfig {
  loginLogsDays: number;
  operationLogsDays: number;
  terminalCommandAuditDays: number;
  terminalFileAuditDays: number;
  terminalSessionDays: number;
  rdpRecordingEnabled: boolean;
  rdpRecordingDays: number;
}

export interface TerminalSettingsConfig {
  sshConnectTimeoutSeconds: number;
  sshBannerTimeoutSeconds: number;
  sshAuthTimeoutSeconds: number;
  sshConnectAttempts: number;
  sshRetryDelayMs: number;
  sshKeepaliveSeconds: number;
  webSocketHeartbeatSeconds: number;
  idleDisconnectMinutes: number;
  initialReadTimeoutSeconds: number;
  initialReadIdleTimeoutMs: number;
  commandReadTimeoutSeconds: number;
  commandReadIdleTimeoutMs: number;
  readerPollIntervalMs: number;
  cwdHookSuppressEchoMs: number;
  cwdHookDrainTimeoutMs: number;
  cwdHookDrainIdleTimeoutMs: number;
  defaultCols: number;
  defaultRows: number;
  defaultFontSize: number;
  scrollbackLines: number;
  bulkExecutionMaxTargets: number;
}

export interface AuthSessionConfig {
  loginExpiryMinutes: number;
}

export type UiThemePreset = 'neutral' | 'slate' | 'blue' | 'cyan' | 'teal' | 'emerald' | 'custom';

export interface UiThemeConfig {
  preset: UiThemePreset;
  customPrimary: string;
}

export interface SiteIdentityConfig {
  appName: string;
  appShortName: string;
  appSubtitle: string;
  browserTitle: string;
  logoText: string;
  logoImageUrl: string;
  iconUrl: string;
  totpIssuer: string;
}

export interface DashboardHeroConfig {
  badgeTemplate: string;
  line1Template: string;
  line2Template: string;
  descriptionTemplate: string;
  font: string;
  fontSize: number;
  fontWeight: number;
  letterSpacing: string;
  durationMs: number;
  pauseMs: number;
  color: string;
  backgroundColor: string;
  centered: boolean;
  verticalCentered: boolean;
  multiline: boolean;
  repeat: boolean;
  random: boolean;
  width: number;
  height: number;
}

export interface LayoutFooterConfig {
  enabled: boolean;
  textTemplate: string;
  linkText: string;
  linkUrl: string;
  fontSize: number;
  color: string;
}

export interface LoginContentConfig {
  badgeTemplate: string;
  title: string;
  description: string;
  copyrightTemplate: string;
}

export interface TemplateVariables {
  appName: string;
  appShortName: string;
  appSubtitle: string;
  username: string;
  displayName: string;
  greeting: string;
  date: string;
  time: string;
  weekday: string;
  year: string;
  localIp: string;
  generatedAt: string;
}

export interface DashboardCard {
  key: string;
  label: string;
  value: number;
  changeLabel: string;
  tone: string;
}

export interface DashboardSeriesPoint {
  date: string;
  success: number;
  failed: number;
}

export interface DashboardDistributionItem {
  label: string;
  value: number;
}

export interface DashboardRecentLogin {
  id: number;
  username: string;
  userDisplay: string;
  ipAddress: string;
  status: 'success' | 'failed';
  message: string;
  createdAt: string | null;
}

export interface DashboardEgressNetwork {
  ip: string;
  location: string;
  isp: string;
  url: string;
  raw: string;
  checkedAt: string;
  status: 'ok' | 'error';
  error: string;
}

export interface DashboardSummary {
  cards: DashboardCard[];
  users: {
    total: number;
    active: number;
    disabled: number;
    staff: number;
    newThisMonth: number;
    canLogin: number;
  };
  assets: {
    total: number;
    verified: number;
    unverified: number;
    failed: number;
    newThisMonth: number;
    groups: number;
    credentials: number;
    publicIpCount: number;
    cpuCores: number;
    memoryGb: number;
    verificationRate: number;
  };
  loginTrend: DashboardSeriesPoint[];
  assetDistribution: {
    os: DashboardDistributionItem[];
    platform: DashboardDistributionItem[];
    verification: DashboardDistributionItem[];
  };
  recentLogins: DashboardRecentLogin[];
  groupRanking: Array<{ id: number; label: string; value: number }>;
  egressNetwork: DashboardEgressNetwork;
  generatedAt: string;
}

export type SecurityScanStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled';
export type SecurityScanTargetStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
export type SecurityScanSeverity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type SecurityScanCategory = 'baseline' | 'port' | 'cve' | string;

export interface SecurityScanRiskCounts {
  critical: number;
  high: number;
  medium: number;
  low: number;
  info: number;
}

export interface SecurityScanTarget {
  id: number;
  name: string;
  group: number;
  groupName: string;
  privateIp: string;
  port: number;
  loginUser: string;
  os: string;
  systemType: string;
  systemArch: string;
  verified: boolean;
}

export interface SecurityScanModules {
  baseline: boolean;
  ports: boolean;
  cve: boolean;
}

export interface SecurityScanSourceState {
  onlineCveEnabled: boolean;
  nvdApiKeyConfigured: boolean;
  sources: string[];
}

export interface SecurityScanTask {
  id: number;
  name: string;
  status: SecurityScanStatus;
  cancelRequested: boolean;
  targetCount: number;
  completedCount: number;
  failedCount: number;
  riskCounts: SecurityScanRiskCounts;
  scanModules: SecurityScanModules;
  options: Record<string, unknown>;
  vulnerabilitySource: SecurityScanSourceState;
  error: string;
  createdBy: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface SecurityScanTargetResult {
  id: number;
  host: number | null;
  hostName: string;
  hostIp: string;
  hostPort: number;
  loginUser: string;
  os: string;
  systemType: string;
  status: SecurityScanTargetStatus;
  systemInfo: Record<string, unknown>;
  openPorts: Array<{ port: number; service: string; duration?: number }>;
  packageCount: number;
  skippedModules: string[];
  riskCounts: SecurityScanRiskCounts;
  error: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface SecurityScanFinding {
  id: number;
  targetResult: number;
  targetName: string;
  targetIp: string;
  category: SecurityScanCategory;
  severity: SecurityScanSeverity;
  title: string;
  recommendation: string;
  cveId: string;
  packageName: string;
  currentVersion: string;
  fixedVersion: string;
  port: number | null;
  service: string;
  cvss: number | null;
  cwe: string;
  source: string;
}

export interface SecurityScanTaskDetail extends SecurityScanTask {
  targetResults: SecurityScanTargetResult[];
}

export interface SecurityScanFindingPage {
  results: SecurityScanFinding[];
  total: number;
  page: number;
  pageSize: number;
  hasNext: boolean;
}

export interface SecurityScanCreatePayload {
  targetIds: number[];
  portsInput: string;
  scanModules: SecurityScanModules;
  name?: string;
}

export interface SecurityScanSummary {
  riskCounts: SecurityScanRiskCounts;
  taskCounts: {
    total: number;
    running: number;
    failed: number;
  };
  failedTargetCount: number;
  latestTaskId: number | null;
  vulnerabilitySource: SecurityScanSourceState;
}
