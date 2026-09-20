export type BulkExecutionStatus = 'queued' | 'running' | 'completed' | 'failed' | 'canceled';
export type BulkExecutionResultStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped';
export type BulkExecutionType = 'shell' | 'file_upload';

export interface BulkExecutionTarget {
  id: number;
  name: string;
  group: number;
  groupName: string;
  privateIp: string;
  publicIp?: string | null;
  port: number;
  loginUser: string;
  os: string;
  systemType: string;
  systemArch: string;
  verified: boolean;
  error?: string;
}

export interface BulkExecutionTargetGroup {
  key: number;
  label: string;
  count: number;
  children: BulkExecutionTargetGroup[];
}

export interface BulkExecutionTargetTree {
  groups: BulkExecutionTargetGroup[];
  targets: BulkExecutionTarget[];
}

export interface BulkExecutionUploadFile {
  id: number;
  filename: string;
  remotePath: string;
  size: number;
}

export interface BulkTransferItem {
  id: number;
  uploadFile: number;
  remotePath: string;
  size: number;
  status: BulkExecutionResultStatus;
  stdout: string;
  stderr: string;
  error: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface BulkExecutionResult {
  id: number;
  host: number | null;
  hostName: string;
  hostIp: string;
  hostPort: number;
  loginUser: string;
  os: string;
  systemType: string;
  systemArch: string;
  status: BulkExecutionResultStatus;
  stdout: string;
  stderr: string;
  exitCode: number | null;
  error: string;
  outputTruncated: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  transfers: BulkTransferItem[];
}

export interface BulkExecutionTask {
  id: number;
  name: string;
  command: string;
  executionType: BulkExecutionType;
  remoteDirectory: string;
  uploadFilename: string;
  uploadSize: number;
  status: BulkExecutionStatus;
  cancelRequested: boolean;
  targetCount: number;
  completedCount: number;
  successCount: number;
  failedCount: number;
  skippedCount: number;
  error: string;
  createdBy: string;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface BulkExecutionTaskDetail extends BulkExecutionTask {
  uploadFiles: BulkExecutionUploadFile[];
  results: BulkExecutionResult[];
}

export interface BulkExecutionTaskPage {
  count: number;
  page: number;
  pageSize: number;
  results: BulkExecutionTask[];
}

export interface BulkExecutionCreatePayload {
  targetIds: number[];
  command: string;
  executionType: Exclude<BulkExecutionType, 'file_upload'>;
  name: string;
}

export interface BulkFileUploadCreatePayload {
  targetIds: number[];
  remoteDirectory: string;
  files: File[];
  file?: File;
  relativePaths?: string[];
  overwrite?: boolean;
  name: string;
}

export interface BulkUploadDuplicateFiles {
  targetId: number;
  hostName: string;
  hostIp: string;
  filenames: string[];
}

export interface BulkUploadCheckPayload {
  targetIds: number[];
  remoteDirectory: string;
  filenames: string[];
  totalSize: number;
}

export interface BulkUploadCheckResult {
  connectedTargets: BulkExecutionTarget[];
  unreachableTargets: BulkExecutionTarget[];
  duplicateFiles: BulkUploadDuplicateFiles[];
  usableTargetIds: number[];
}
