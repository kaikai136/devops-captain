<script setup lang="ts">
const previewRows = [{ group: 'default', name: 'host-01', ip: '192.168.1.10', os: 'linux', port: 22, remark: '' }];

const emit = defineEmits<{
  close: [];
  confirm: [];
  'download-template': [];
}>();
</script>

<template>
  <el-dialog class="host-transfer-modal host-import-modal" :model-value="true" title="导入主机表格" width="720px" :close-on-click-modal="false" @close="emit('close')">
      <div class="popup-body">
        <h2>导入主机表格</h2>
        <div class="host-import-body">
          <p>模板只导入主机基础信息，已存在的主机将跳过保留。</p>
          <el-table :data="previewRows" class="host-import-template-preview app-data-table" size="small">
            <el-table-column prop="group" label="主机分组" />
            <el-table-column prop="name" label="节点" />
            <el-table-column prop="ip" label="IP地址" />
            <el-table-column prop="os" label="平台类型" />
            <el-table-column prop="port" label="端口" />
            <el-table-column prop="remark" label="备注" />
          </el-table>
        </div>
      </div>
      <template #footer>
        <div class="modal-actions popup-footer popup-actions">
          <el-button @click="emit('close')">取消</el-button>
          <el-button @click="emit('download-template')">下载导入模板</el-button>
          <el-button class="primary" type="primary" @click="emit('confirm')">直接导入</el-button>
        </div>
      </template>
  </el-dialog>
</template>
