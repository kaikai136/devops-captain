# Bulk Upload Required Fields And Folder Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make bulk execution and upload forms visibly mark required fields, validate missing values when actions are clicked, and support file/folder uploads while preserving each file's local relative directory path.

**Architecture:** Keep the existing `BulkExecutionTask` and upload metadata models. The frontend will carry one `relativePaths` entry per selected `File`, send those entries in the same order as multipart `files`, and show the relative path in the selection list. The backend will normalize and validate each relative path, store it in `BulkExecutionUploadFile.filename`, derive the remote path with `join_remote_path`, check duplicates using the complete path, and create remote parent directories before copying nested files.

**Tech Stack:** Django REST Framework, Django TestCase, Paramiko/SSH/SFTP, Vue 3, TypeScript, Vitest.

## Global Constraints

- Preserve the existing `BulkExecutionTask`, `BulkExecutionUploadFile`, and `BulkExecutionTransferItem` contracts; no new database field or migration is required.
- Required-field buttons stay clickable when values are missing so click handlers can display the first missing-field toast; only permission, active operation, confirmation, and other non-validation states may disable them.
- `relativePaths` is positional: item `relativePaths[index]` describes multipart `files[index]`.
- Accept POSIX-style relative paths after normalizing `\` to `/`; reject empty paths, absolute paths, drive-letter paths, `.`/`..` segments, control characters, empty path segments, and paths longer than the existing filename limit.
- Preserve existing single-file and flat multi-file behavior by falling back to `File.name` when no relative path is provided.
- Keep user-facing copy in the existing Chinese UI style and use the existing `showToast` and `errorMessage` helpers.

---

### Task 1: Backend Relative-Path Upload Contract

**Files:**
- Modify: `backend/bulk_execution/views.py:95-111`
- Modify: `backend/bulk_execution/services.py:16-177,270-310`
- Modify: `backend/bulk_execution/tests.py` in `BulkExecutionApiTests`
- Modify: `backend/bulk_execution/tests.py` in `BulkExecutionRunnerTests`
- Test: `backend/web_terminal/tests/test_file_parsers.py` only if the shared relative-path helper needs an additional boundary test

**Interfaces:**
- Consumes: multipart `files` and repeated multipart `relativePaths`, or direct service calls with `relative_paths: list[str] | None`.
- Produces: `BulkExecutionUploadFile.filename` as a safe local relative path such as `release/config/app.yml`.
- Produces: `BulkExecutionUploadFile.remote_path` and transfer `remote_path` as `/tmp/release/config/app.yml`.
- Produces: duplicate-check requests that pass complete relative filenames to `inspect_bulk_upload_target`.
- Produces: per-file remote parent-directory creation as part of the shared SFTP/SSH upload flow.

- [ ] **Step 1: Write failing backend tests for nested paths, positional metadata, and unsafe paths**

Add tests next to the existing multipart upload tests:

```python
@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="bulk-upload-relative-test-"))
def test_create_file_upload_task_preserves_relative_paths(self):
    self.grant("access_bulkExecution", "action_bulkExecution_execute")
    config = SimpleUploadedFile("app.yml", b"name: api\n", content_type="text/yaml")
    script = SimpleUploadedFile("start.sh", b"#!/bin/sh\n", content_type="text/plain")

    with patch("bulk_execution.views.start_bulk_execution_task"):
        response = self.client.post(
            "/api/bulk-execution/tasks/",
            data={
                "executionType": "file_upload",
                "targetIds": json.dumps([self.linux.id]),
                "remoteDirectory": "/tmp/",
                "name": "release upload",
                "files": [config, script],
                "relativePaths": ["release/config/app.yml", "release/bin/start.sh"],
            },
        )

    self.assertEqual(response.status_code, 201)
    task = BulkExecutionTask.objects.get(name="release upload")
    upload_files = list(task.upload_files.order_by("id"))
    self.assertEqual([item.filename for item in upload_files], ["release/config/app.yml", "release/bin/start.sh"])
    self.assertEqual(
        [item.remote_path for item in upload_files],
        ["/tmp/release/config/app.yml", "/tmp/release/bin/start.sh"],
    )

def test_create_file_upload_task_rejects_unsafe_relative_paths(self):
    self.grant("access_bulkExecution", "action_bulkExecution_execute")
    for relative_path in ["/etc/passwd", "../secret", "release/../../secret", "C:/secret"]:
        upload = SimpleUploadedFile("payload.txt", b"payload", content_type="text/plain")
        response = self.client.post(
            "/api/bulk-execution/tasks/",
            data={
                "executionType": "file_upload",
                "targetIds": json.dumps([self.linux.id]),
                "remoteDirectory": "/tmp/",
                "name": "unsafe upload",
                "files": [upload],
                "relativePaths": [relative_path],
            },
        )
        self.assertEqual(response.status_code, 400, relative_path)
        self.assertFalse(BulkExecutionTask.objects.filter(name="unsafe upload").exists())
```

- [ ] **Step 2: Run the new backend tests and confirm the expected contract failure**

Run from `backend`:

```powershell
python manage.py test bulk_execution.tests.BulkExecutionApiTests.test_create_file_upload_task_preserves_relative_paths bulk_execution.tests.BulkExecutionApiTests.test_create_file_upload_task_rejects_unsafe_relative_paths
```

Expected: FAIL because the API currently ignores `relativePaths` and normalizes every upload to `item.name`.

- [ ] **Step 3: Add a positional relative-path parser and safe normalizer**

In `backend/bulk_execution/services.py`, add a helper near `normalize_uploaded_files`:

```python
def relative_paths_for_upload(payload: dict, uploaded_files: list) -> list[str]:
    raw_paths = payload.getlist("relativePaths") if hasattr(payload, "getlist") else payload.get("relativePaths")
    if raw_paths is None:
        raw_paths = payload.get("relative_paths") if isinstance(payload, dict) else None
    if raw_paths is None:
        raw_paths = [getattr(item, "name", "") for item in uploaded_files]
    elif isinstance(raw_paths, str):
        try:
            decoded = json.loads(raw_paths)
        except (TypeError, ValueError):
            decoded = [raw_paths]
        raw_paths = decoded
    if not isinstance(raw_paths, list) or len(raw_paths) != len(uploaded_files):
        raise ValueError("Uploaded file information is incomplete")
    return [normalize_upload_relative_path(value) for value in raw_paths]


def normalize_upload_relative_path(value: str) -> str:
    normalized = normalize_remote_relative_file_path(value)
    parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("Upload relative path is invalid")
    if re.fullmatch(r"[A-Za-z]:", parts[0]):
        raise ValueError("Upload relative path is invalid")
    if any(any(ord(char) < 32 or ord(char) == 127 for char in part) for part in parts):
        raise ValueError("Upload relative path is invalid")
    if len(normalized) > BulkExecutionUploadFile._meta.get_field("filename").max_length:
        raise ValueError("Upload relative path is too long")
    return normalized
```

Import `re` and `normalize_remote_relative_file_path`, then use the returned list in `create_bulk_file_upload_task`. Compare duplicate names using the normalized full relative path, and use that same value for `join_remote_path`. Keep the existing basename fallback for callers that do not provide metadata.

- [ ] **Step 4: Update the multipart view to pass all selected paths**

Keep `request.FILES.getlist("files")` as the source of file order and pass the multipart payload directly to `create_bulk_file_upload_task`; the service helper must read `relativePaths` with `getlist` so repeated form fields are not collapsed to one value. Preserve the existing `file` fallback for legacy single-file clients.

- [ ] **Step 5: Add duplicate-check coverage for nested relative paths**

Add a test that posts `filenames=["release/config/app.yml", "release/bin/start.sh"]`, asserts the mocked inspector receives those exact values, and asserts duplicate output contains the nested path. Update the existing flat test only where needed to preserve its current expected behavior.

- [ ] **Step 6: Implement the backend contract and run the API tests**

Run:

```powershell
python manage.py test bulk_execution.tests.BulkExecutionApiTests
```

Expected: all `BulkExecutionApiTests` pass, including the existing flat/multi-file upload tests.

- [ ] **Step 7: Write a failing runner test for remote parent directories**

Extend the multi-file runner test with nested paths and assert that every upload calls the shared streaming transfer service with the nested parent directory and final filename.

Use this focused assertion shape:

```python
self.assertEqual(
    [(directory, filename) for directory, filename, _ in calls],
    [
        ("/srv/app/release/config", "app.yml"),
    ],
)
```

- [ ] **Step 8: Implement parent-directory creation and failure propagation**

In `run_upload_file_item`, derive the parent with `parent_remote_path(upload_file.remote_path)` and pass the file stream to the shared remote-file upload service. The SFTP path creates missing parent directories and writes to a temporary remote file before rename; the SSH-stream fallback performs the same parent-directory and atomic-replacement flow. Propagate transfer failures to the matching host result and do not construct a shell command from an unvalidated client path.

- [ ] **Step 9: Run all backend bulk-execution tests**

Run from `backend`:

```powershell
python manage.py test bulk_execution
```

Expected: all bulk execution API and runner tests pass with no migration changes.

### Task 2: Frontend Required Validation And Folder Upload

**Files:**
- Modify: `frontend/src/features/bulk-execution/types.ts`
- Modify: `frontend/src/features/bulk-execution/api/bulkExecution.ts`
- Modify: `frontend/src/features/bulk-execution/components/BulkExecutionPanel.vue`
- Modify: `frontend/src/styles/tools/bulk-execution.css`
- Test: `frontend/src/features/bulk-execution/__tests__/bulkExecution.structure.test.ts`

**Interfaces:**
- Consumes: `File.webkitRelativePath` when supplied by a directory picker; otherwise `File.name`.
- Produces: `BulkFileUploadCreatePayload.relativePaths?: string[]`.
- Produces: multipart `relativePaths` repeated in the same order as multipart `files`.
- Produces: upload-check `filenames` containing normalized local relative paths.
- Produces: toast validation for the first missing required execute/upload field.

- [ ] **Step 1: Write failing frontend structure tests**

Append focused tests to `bulkExecution.structure.test.ts`:

```ts
it('marks required bulk fields and validates actions on click', () => {
  const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');

  expect(panel).toContain('required-marker');
  expect(panel).toContain('validateExecuteForm');
  expect(panel).toContain('validateUploadForm');
  expect(panel).toContain('请填写任务名称');
  expect(panel).toContain('请选择目标机器');
  expect(panel).toContain('请选择上传文件或文件夹');
  expect(panel).toContain('请填写远程目录');
  expect(panel).toContain('@click="createTaskWithConfirmation"');
  expect(panel).toContain('@click="submitUploadFlow"');
});

it('supports folder selection and preserves relative paths through upload APIs', () => {
  const panel = readSource('features/bulk-execution/components/BulkExecutionPanel.vue');
  const api = readSource('features/bulk-execution/api/bulkExecution.ts');
  const types = readSource('features/bulk-execution/types.ts');

  expect(panel).toContain('uploadFolderInput');
  expect(panel).toContain('webkitdirectory');
  expect(panel).toContain('webkitRelativePath');
  expect(panel).toContain('relativePaths');
  expect(api).toContain("form.append('relativePaths'");
  expect(types).toContain('relativePaths');
});
```

- [ ] **Step 2: Run the frontend tests and confirm they fail for missing implementation**

Run from `frontend`:

```powershell
npm run test:run -- src/features/bulk-execution/__tests__/bulkExecution.structure.test.ts
```

Expected: FAIL because the current panel has no required markers, validation helpers, folder input, or relative-path multipart field.

- [ ] **Step 3: Extend the upload types and API helper**

In `BulkFileUploadCreatePayload`, add:

```ts
relativePaths?: string[];
```

In `createBulkFileUploadTask`, calculate:

```ts
const relativePaths = payload.relativePaths?.length
  ? payload.relativePaths
  : files.map((file) => (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name);
```

Append one `relativePaths` form value after each corresponding `files` value. Keep existing fields and the single-file fallback unchanged.

- [ ] **Step 4: Add required-field state and click-time validation**

In `BulkExecutionPanel.vue`, replace validation-only `canCreateTask`, `canCheckUpload`, and `canCreateUpload` gating with action-state computeds that only account for permission and active busy states. Add:

```ts
function showMissingField(message: string) {
  showToast("请填写必填项", message, "error");
  return false;
}

function validateExecuteForm() {
  if (!taskName.value.trim()) return showMissingField("请填写任务名称");
  if (!selectedTargetIds.value.size) return showMissingField("请选择目标机器");
  if (!commandInput.value.trim()) return showMissingField("请填写脚本内容");
  return true;
}

function validateUploadForm() {
  if (!taskName.value.trim()) return showMissingField("请填写任务名称");
  if (!selectedTargetIds.value.size) return showMissingField("请选择目标机器");
  if (!selectedUploadFiles.value.length) return showMissingField("请选择上传文件或文件夹");
  if (!remoteDirectory.value.trim()) return showMissingField("请填写远程目录");
  return true;
}
```

Call `validateExecuteForm()` at the start of `createTaskWithConfirmation`, and call `validateUploadForm()` at the start of `checkBulkUpload`, `submitUploadFlow`, and `createUploadTask`. Keep permission, active request, and overwrite-confirmation disabling behavior.

- [ ] **Step 5: Add red required markers and keep buttons clickable for validation**

Add `<em class="required-marker">*</em>` after the task name, script content, target machine, upload file/folder, and remote directory labels/headings. Change the execute/check/upload button bindings so missing values do not make the button disabled; busy and permission states remain disabled. The upload submit handler must still validate before checking or creating a task.

- [ ] **Step 6: Add file and folder inputs with relative-path extraction**

Add a second hidden input:

```vue
<input ref="uploadFolderInput" hidden type="file" webkitdirectory directory multiple @change="onUploadFolderChange" />
```

Add `triggerUploadFolderSelect`, `onUploadFolderChange`, and `relativePathForFile`:

```ts
function relativePathForFile(file: File) {
  return (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
}

function onUploadFolderChange(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files ?? []);
  if (files.length) selectedUploadFiles.value = mergeFiles(selectedUploadFiles.value, files);
  (event.target as HTMLInputElement).value = "";
}
```

Use the relative path in `mergeFiles` duplicate detection, upload-check `filenames`, multipart `relativePaths`, the selected-file list, and the task-detail upload-file display. Keep drag-and-drop behavior and the existing file picker.

- [ ] **Step 7: Add compact folder/file selection styling**

Update `bulk-execution.css` so the drop zone can contain two selection buttons, relative paths wrap or ellipsize without changing row height, and the red marker is visually consistent:

```css
.required-marker {
  color: var(--bulk-danger);
  font-style: normal;
}

.bulk-upload-select-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
```

Keep existing card radii, colors, and responsive grid behavior; do not add a new page-level card or broad layout refactor.

- [ ] **Step 8: Run the focused frontend tests**

Run:

```powershell
npm run test:run -- src/features/bulk-execution/__tests__/bulkExecution.structure.test.ts
```

Expected: all bulk execution structure tests pass.

### Task 3: Full Verification And Quality Review

**Files:**
- Review: `backend/bulk_execution/views.py`
- Review: `backend/bulk_execution/services.py`
- Review: `backend/bulk_execution/tests.py`
- Review: `frontend/src/features/bulk-execution/api/bulkExecution.ts`
- Review: `frontend/src/features/bulk-execution/types.ts`
- Review: `frontend/src/features/bulk-execution/components/BulkExecutionPanel.vue`
- Review: `frontend/src/styles/tools/bulk-execution.css`

**Interfaces:**
- Consumes: the passing backend and frontend tests from Tasks 1 and 2.
- Produces: verified required-field prompts, safe nested upload paths, and a successful frontend build.

- [ ] **Step 1: Run the complete backend test suite for the changed app**

From `backend`:

```powershell
python manage.py test bulk_execution
```

Expected: exit code 0 and all tests passing.

- [ ] **Step 2: Run the complete focused frontend test set**

From `frontend`:

```powershell
npm run test:run -- src/features/bulk-execution/__tests__/bulkExecution.structure.test.ts src/components/terminal/__tests__/SimpleHostTerminalPage.structure.test.ts
```

Expected: exit code 0 and all listed tests passing.

- [ ] **Step 3: Build the frontend**

From `frontend`:

```powershell
npm run build
```

Expected: exit code 0 with the production bundle generated successfully.

- [ ] **Step 4: Perform the code-quality security review**

Inspect the final diff for:

- path traversal, absolute-path, drive-letter, control-character, and duplicate-path rejection;
- shell quoting for remote parent and destination paths;
- no upload metadata/file-count misalignment;
- no validation bypass caused by stale `uploadCheckResult`;
- no disabled button preventing the required-field toast;
- no unbounded file-list rendering or layout overflow on narrow screens.

Fix any in-scope issue found, rerun the affected test, then rerun the full commands above before reporting the result.
