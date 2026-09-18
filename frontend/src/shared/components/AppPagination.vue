<script setup lang="ts">
defineProps<{
  page: number;
  pageSize: number;
  total: number;
}>();

const emit = defineEmits<{
  'page-change': [page: number];
  'page-size-change': [pageSize: number];
}>();
</script>

<template>
  <el-pagination
    class="app-pagination"
    background
    layout="total, sizes, prev, pager, next, jumper"
    :current-page="page"
    :page-size="pageSize"
    :page-sizes="[10, 20, 50, 100, 200]"
    :total="total"
    @current-change="emit('page-change', $event)"
    @size-change="emit('page-size-change', $event)"
  />
</template>
