<template>
  <div class="audit-container">
    <!-- Filter -->
    <el-card shadow="hover" style="margin-bottom: 16px">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select v-model="filter.action" placeholder="操作类型" clearable style="width: 100%">
            <el-option label="全部" value="" />
            <el-option label="登录" value="login" />
            <el-option label="扫描" value="scan" />
            <el-option label="配置" value="config" />
            <el-option label="系统" value="system" />
          </el-select>
        </el-col>
        <el-col :span="4">
          <el-button type="primary" @click="loadLogs">查询</el-button>
          <el-button @click="filter.action = ''; loadLogs()">重置</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- Log table -->
    <el-card shadow="hover">
      <el-table :data="logs" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="timestamp" label="时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="action" label="操作类型" width="100">
          <template #default="{ row }">
            <el-tag :type="actionTag(row.action)" size="small" effect="plain">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource" label="资源" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user" label="用户" width="120" />
        <el-table-column label="详情" min-width="200">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="toggleDetail(row)">
              {{ expandedRows.has(row) ? '收起' : '查看详情' }}
            </el-button>
            <div v-if="expandedRows.has(row)" style="margin-top: 8px; padding: 8px; background: #f5f7fa; border-radius: 4px; font-size: 13px; white-space: pre-wrap">
              {{ row.detail || '无详细信息' }}
            </div>
          </template>
        </el-table-column>
      </el-table>

      <!-- Pagination -->
      <div style="display: flex; justify-content: flex-end; margin-top: 16px">
        <el-pagination
          v-model:current-page="page"
          :page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          @current-change="loadLogs"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import * as api from '../api'

const loading = ref(false)
const logs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const expandedRows = ref(new Set())

const filter = reactive({
  action: '',
})

function formatTime(ts) {
  if (!ts) return '-'
  return ts.slice(0, 19).replace('T', ' ')
}

function actionTag(action) {
  if (!action) return 'info'
  const a = (action || '').toLowerCase()
  if (a.includes('登录') || a === 'login') return 'success'
  if (a.includes('扫描') || a === 'scan') return 'warning'
  if (a.includes('配置') || a === 'config') return 'primary'
  if (a.includes('系统') || a === 'system') return 'danger'
  return 'info'
}

function toggleDetail(row) {
  const s = expandedRows.value
  s.has(row) ? s.delete(row) : s.add(row)
}

async function loadLogs() {
  loading.value = true
  try {
    const offset = (page.value - 1) * pageSize
    const res = await api.listAuditLogs(pageSize, offset, filter.action)
    const data = res.data
    if (Array.isArray(data)) {
      logs.value = data
      total.value = data.length
    } else {
      logs.value = data?.logs || data?.items || data?.results || []
      total.value = data?.total || data?.count || logs.value.length
    }
  } catch {
    // keep empty
  } finally {
    loading.value = false
  }
}

onMounted(loadLogs)
</script>

<style scoped>
.audit-container {
  max-width: 1200px;
  margin: 0 auto;
}
</style>
