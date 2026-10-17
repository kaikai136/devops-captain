<script setup lang="ts">
import { ref } from 'vue';
import type { SftpFileUploadItem } from '../../composables/useSftpBrowser';
import { folderUploadItems } from '../../utils/folderUpload';

const emit = defineEmits<{ selected: [items: SftpFileUploadItem[]] }>();
const fileInput = ref<HTMLInputElement | null>(null);
const folderInput = ref<HTMLInputElement | null>(null);
const contentsFolderInput = ref<HTMLInputElement | null>(null);

function openFile() { fileInput.value?.click() }
function openFolder() { folderInput.value?.click() }
function openFolderContents() { contentsFolderInput.value?.click() }
function onFile(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = '';
  if (file) emit('selected', [{ file }]);
}
function onFolder(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = '';
  if (files.length) emit('selected', folderUploadItems(files, false));
}
function onFolderContents(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  input.value = '';
  if (files.length) emit('selected', folderUploadItems(files, true));
}

defineExpose({ openFile, openFolder, openFolderContents });
</script>

<template>
  <input ref="fileInput" hidden type="file" @change="onFile" />
  <input ref="folderInput" hidden type="file" multiple webkitdirectory @change="onFolder" />
  <input ref="contentsFolderInput" hidden type="file" multiple webkitdirectory @change="onFolderContents" />
</template>
