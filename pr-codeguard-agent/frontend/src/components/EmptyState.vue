<template>
  <div style="text-align: center; padding: 40px; color: #909399">
    <el-icon style="font-size: 48px; margin-bottom: 12px">
      <InfoFilled />
    </el-icon>
    <h4 style="margin: 0 0 8px">{{ title }}</h4>
    <p style="margin: 0; font-size: 13px">{{ description }}</p>
  </div>
</template>

<script setup>
import { InfoFilled } from '@element-plus/icons-vue'
defineProps({
  title: { type: String, default: '无数据' },
  description: { type: String, default: '' },
})
</script>
