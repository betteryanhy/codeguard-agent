<template>
  <div class="tasks-container">
    <!-- Filter bar -->
    <el-card shadow="hover" style="margin-bottom: 16px">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-select v-model="filter.status" placeholder="状态筛选" clearable style="width: 100%">
            <el-option label="全部" value="" />
            <el-option label="待处理" value="pending" />
            <el-option label="运行中" value="running" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-col>
        <el-col :span="8">
          <el-input v-model="filter.repoQuery" placeholder="搜索仓库 URL..." clearable prefix-icon="Search" />
        </el-col>
        <el-col :span="4">
          <el-button type="primary" @click="loadTasks">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </el-col>
      </el-row>
    </el-card>

    <!-- Task table -->
    <el-card shadow="hover">
      <el-table :data="tasks" stripe v-loading="loading" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="repo_url" label="仓库" min-width="200" show-overflow-tooltip />
        <el-table-column prop="mr_id" label="MR ID" width="80" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="dark">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="发现数" width="80">
          <template #default="{ row }">
            {{ findingCount(row) }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="viewResult(row)">查看结果</el-button>
            <el-button
              v-if="row.status === 'failed'"
              size="small"
              type="warning"
              link
              :loading="retrying[row.id]"
              @click="handleRetry(row)"
            >重试</el-button>
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
          @current-change="loadTasks"
        />
      </div>
    </el-card>

    <!-- Result dialog -->
    <el-dialog v-model="resultDialog.visible" title="扫描结果" width="800px" :close-on-click-modal="false">
      <div v-loading="resultDialog.loading">
        <el-table v-if="resultDialog.findings.length" :data="resultDialog.findings" stripe style="width:100%" max-height="400">
          <el-table-column label="引擎" width="90">
            <template #default="{ row }">
              <el-tag :type="engineTagType(row.engine)" size="small" effect="plain">{{ row.engine || 'trivy' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="严重级别" width="80">
            <template #default="{ row }">
              <span :class="'sev-tag ' + (row.severity || 'info').toLowerCase()">
                {{ (row.severity || 'INFO').toUpperCase() }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="描述" min-width="180">
            <template #default="{ row }">{{ row.message }}</template>
          </el-table-column>
          <el-table-column label="文件位置" min-width="140">
            <template #default="{ row }">
              <code style="font-size:12px">{{ row.file_path }}{{ row.line ? ':' + row.line : '' }}</code>
            </template>
          </el-table-column>
        </el-table>
        <EmptyState v-else title="无发现" description="该任务未扫描到任何问题" />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'
import EmptyState from '../components/EmptyState.vue'

const loading = ref(false)
const tasks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const retrying = reactive({})

const filter = reactive({
  status: '',
  repoQuery: '',
})

const resultDialog = reactive({
  visible: false,
  loading: false,
  content: '',
  findings: [],
})

function statusTag(status) {
  const map = { pending: 'info', running: 'warning', completed: 'success', failed: 'danger' }
  return map[status] || 'info'
}

function statusLabel(status) {
  const map = { pending: '待处理', running: '运行中', completed: '已完成', failed: '失败' }
  return map[status] || status
}

function formatTime(ts) {
  if (!ts) return '-'
  return ts.slice(0, 19).replace('T', ' ')
}

function findingCount(row) {
  const bySev = row.summary?.by_severity || row.result_summary?.by_severity || {}
  return (bySev.critical || 0) + (bySev.major || 0) + (bySev.minor || 0) || 0
}

function resetFilter() {
  filter.status = ''
  filter.repoQuery = ''
  page.value = 1
  loadTasks()
}

async function loadTasks() {
  loading.value = true
  try {
    const skip = (page.value - 1) * pageSize
    const res = await api.listTasks(skip, pageSize)
    const data = res.data
    let items = []
    let totalCount = 0
    if (Array.isArray(data)) {
      items = data
      totalCount = data.length
    } else {
      items = data?.items || data?.rows || data?.results || []
      totalCount = data?.total || data?.count || items.length
    }

    // Apply local filters
    if (filter.status) {
      items = items.filter(t => t.status === filter.status)
    }
    if (filter.repoQuery) {
      const q = filter.repoQuery.toLowerCase()
      items = items.filter(t => (t.repo_url || '').toLowerCase().includes(q))
    }

    tasks.value = items
    total.value = totalCount
  } catch (e) {
    ElMessage.error('加载任务列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function viewResult(row) {
  resultDialog.loading = true
  resultDialog.visible = true
  try {
    const res = await api.getResult(row.id)
    const data = res.data
    resultDialog.content = data
    resultDialog.findings = data.findings || data.results || []
  } catch (e) {
    console.error('Failed to load result:', e)
    ElMessage.error('加载扫描结果失败')
  } finally {
    resultDialog.loading = false
  }
}

function engineTagType(engine) {
  const map = { trivy: '', iac: 'warning', secrets: 'danger', sast: 'info', best_practice: 'success' }
  return map[(engine || '').toLowerCase()] || ''
}

async function handleRetry(row) {
  retrying[row.id] = true
  try {
    await api.retryTask(row.id)
    ElMessage.success('任务已重新提交')
    await loadTasks()
  } catch (e) {
    ElMessage.error('重试失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    retrying[row.id] = false
  }
}

onMounted(loadTasks)
</script>

<style scoped>
.tasks-container {
  max-width: 1200px;
  margin: 0 auto;
}
.sev-tag { display:inline-block; padding:0 6px; border-radius:3px; font-size:12px; font-weight:600; font-family:var(--font-mono, monospace); }
.sev-tag.critical { color:#f56c6c; background:#fef0f0; }
.sev-tag.major { color:#e6a23c; background:#fdf6ec; }
.sev-tag.minor { color:#409eff; background:#ecf5ff; }
.sev-tag.info { color:#909399; background:#f4f4f5; }
</style>
