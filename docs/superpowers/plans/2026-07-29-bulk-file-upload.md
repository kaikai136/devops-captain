# Bulk File Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single-file upload action to host batch operations, implemented as a bulk execution task that copies the file to selected Linux SSH hosts.

**Architecture:** Extend `BulkExecutionTask` with a `file_upload` execution type plus remote path and uploaded-file metadata. The API accepts multipart form data, persists the uploaded file in Django storage, and the runner streams files through the shared SFTP/SSH transfer service while reusing current polling/result UI.

**Tech Stack:** Django REST Framework, Django model migrations, Paramiko/SSH/SFTP, Vue 3, TypeScript, Vitest.

## Global Constraints

- Reuse the existing `bulk_execution` permissions and task history.
- Support one uploaded file per task, with remote directory defaulting to `/tmp/`.
- Upload only to executable Linux SSH targets selected in the batch operation.
- Keep UI copy in Chinese and follow current component styling.
- Validate target selection, file presence, and remote directory before starting a task.

---

### Task 1: Backend File Upload Task Contract

**Files:**
- Modify: `backend/bulk_execution/models.py`
- Modify: `backend/bulk_execution/serializers.py`
- Modify: `backend/bulk_execution/views.py`
- Modify: `backend/bulk_execution/services.py`
- Create: `backend/bulk_execution/migrations/0003_bulk_file_upload.py`
- Test: `backend/bulk_execution/tests.py`

**Interfaces:**
- Consumes: existing `create_bulk_execution_task(user, payload) -> BulkExecutionTask`
- Produces: `create_bulk_file_upload_task(user, payload, uploaded_file) -> BulkExecutionTask`
- Produces: `BulkExecutionTask.EXECUTION_FILE_UPLOAD = "file_upload"`
- Produces serialized fields `remoteDirectory`, `uploadFilename`, `uploadSize`

- [ ] Write tests that multipart upload creates a `file_upload` task with selected executable hosts and starts the runner.
- [ ] Write tests that `run_bulk_execution_task` streams the uploaded file through the shared remote-file transfer service when task type is `file_upload`.
- [ ] Verify backend tests fail before implementation.
- [ ] Add model fields, migration, serializer fields, API branch, validation, storage cleanup, and runner copy logic.
- [ ] Verify backend tests pass.

### Task 2: Frontend Upload API And UI

**Files:**
- Modify: `frontend/src/features/bulk-execution/types.ts`
- Modify: `frontend/src/features/bulk-execution/api/bulkExecution.ts`
- Modify: `frontend/src/features/bulk-execution/components/BulkExecutionPanel.vue`
- Modify: `frontend/src/features/hosts/components/HostTable.vue`
- Modify: `frontend/src/features/hosts/components/HostToolbar.vue`
- Modify: `frontend/src/features/hosts/components/HostManager.vue`
- Modify: `frontend/src/styles/tools/bulk-execution.css`
- Test: `frontend/src/features/bulk-execution/__tests__/bulkExecution.structure.test.ts`
- Test: `frontend/src/features/hosts/components/__tests__/HostManager.structure.test.ts`

**Interfaces:**
- Consumes: `createBulkFileUploadTask(payload: BulkFileUploadCreatePayload)`
- Produces: session storage key `ops-tool.bulk-execution.upload-target-ids`
- Produces: `upload-file-selected` event from host toolbar/table

- [ ] Write structure tests for the upload API helper, upload modal, and batch operation upload button.
- [ ] Verify frontend tests fail before implementation.
- [ ] Add API FormData helper and typed `file_upload` task fields.
- [ ] Add batch action button in host toolbar/table that opens bulk execution in upload mode with selected IDs.
- [ ] Add upload modal to `BulkExecutionPanel.vue` with hidden file input/drop zone, remote directory, selected target picker, create call, and result labels.
- [ ] Add scoped CSS for the upload dialog/drop zone using existing modal styles.
- [ ] Verify frontend tests pass.

### Task 3: Final Verification

**Files:**
- Review: all modified backend and frontend files

**Interfaces:**
- Consumes: backend and frontend tests from Tasks 1 and 2
- Produces: verified working change

- [ ] Run targeted backend tests: `python manage.py test bulk_execution`
- [ ] Run targeted frontend tests: `npm run test:run -- bulkExecution.structure.test.ts HostManager.structure.test.ts`
- [ ] Run frontend type/build check: `npm run build`
- [ ] Review diff for file upload security, validation, stale state, and UI consistency.
