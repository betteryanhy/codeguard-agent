<template>
  <div>
    <!-- Search input -->
    <div style="margin-bottom: 16px">
      <el-input
        v-model="searchQuery"
        placeholder="按仓库 URL 过滤..."
        clearable
        style="width: 360px"
        :prefix-icon="Search"
      />
    </div>

    <!-- Tasks table -->
    <el-table
      :data="filteredTasks"
      v-loading="loading"
      stripe
      border
      style="width: 100%"
      @row-click="handleRowClick"
    >
      <el-table-column prop="id" label="任务ID" width="80" />
      <el-table-column prop="repo_url" label="仓库URL" min-width="240" show-overflow-tooltip />
      <el-table-column prop="mr_id" label="MR ID" width="100" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusType(row.status)" effect="plain" size="small">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="发现数" width="90" align="center">
        <template #default="{ row }">
          {{ row.findings?.length ?? 0 }}
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="180">
        <template #default="{ row }">
          {{ row.created_at ? new Date(row.created_at).toLocaleString() : '-' }}
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const router = useRouter()
const loading = ref(false)
const tasks = ref([])
const searchQuery = ref('')

const filteredTasks = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return tasks.value
  return tasks.value.filter((t) => (t.repo_url || '').toLowerCase().includes(q))
})

const statusType = (status) => {
  const map = {
    completed: 'success',
    running: 'warning',
    pending: 'info',
    failed: 'danger',
  }
  return map[status] || 'info'
}

const handleRowClick = (row) => {
  router.push(`/tasks/${row.id}`)
}

const fetchTasks = async () => {
  loading.value = true
  try {
    const res = await api.listTasks(0, 50)
    tasks.value = res.data || []
  } catch (e) {
    ElMessage.error('获取任务列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

onMounted(fetchTasks)
</script>
