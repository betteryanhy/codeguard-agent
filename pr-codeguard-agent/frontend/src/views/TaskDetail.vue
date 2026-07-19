<template>
  <div v-loading="loading" style="min-height: 300px">
    <!-- Task info -->
    <el-descriptions title="任务信息" :column="2" border style="margin-bottom: 24px">
      <el-descriptions-item label="任务ID" width="120">{{ task?.id }}</el-descriptions-item>
      <el-descriptions-item label="仓库">
        {{ task?.repo_url }}
      </el-descriptions-item>
      <el-descriptions-item label="MR ID">{{ task?.mr_id }}</el-descriptions-item>
      <el-descriptions-item label="状态">
        <el-tag :type="statusType(task?.status)" effect="plain" size="small">
          {{ task?.status }}
        </el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="创建时间">
        {{ task?.created_at ? new Date(task.created_at).toLocaleString() : '-' }}
      </el-descriptions-item>
    </el-descriptions>

    <!-- Findings -->
    <template v-if="findings && findings.length > 0">
      <h3 style="margin-bottom: 12px">发现项 ({{ findings.length }})</h3>
      <el-table :data="findings" stripe border style="width: 100%">
        <el-table-column prop="engine" label="引擎" width="120" />
        <el-table-column label="严重级别" width="120">
          <template #default="{ row }">
            <el-tag :type="severityType(row.severity)" effect="dark" size="small">
              {{ row.severity }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file" label="文件路径" min-width="240" show-overflow-tooltip />
        <el-table-column prop="line" label="行号" width="80" align="center" />
        <el-table-column prop="message" label="消息" min-width="300" show-overflow-tooltip />
      </el-table>
    </template>

    <el-empty v-else-if="!loading" description="暂无发现项" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const route = useRoute()
const taskId = route.params.id

const loading = ref(false)
const task = ref(null)
const findings = ref([])

const statusType = (status) => {
  const map = {
    completed: 'success',
    running: 'warning',
    pending: 'info',
    failed: 'danger',
  }
  return map[status] || 'info'
}

const severityType = (severity) => {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'high') return 'danger'
  if (s === 'medium') return 'warning'
  if (s === 'low') return 'info'
  return 'info'
}

const fetchDetail = async () => {
  loading.value = true
  try {
    const res = await api.getResult(taskId)
    const data = res.data || {}
    task.value = data
    findings.value = data.findings || []
  } catch (e) {
    ElMessage.error('获取任务详情失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

onMounted(fetchDetail)
</script>
