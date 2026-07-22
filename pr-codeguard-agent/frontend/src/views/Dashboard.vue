<template>
  <div class="dashboard-container">
    <!-- Stats cards -->
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <el-tooltip content="已接入 GitLab 的代码仓库总数" placement="top" :show-after="300">
            <div class="stat-card-inner">
              <div class="stat-icon" style="background: #e6f7ff; color: #1890ff">
                <el-icon :size="24"><Folder /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ formatCount(stats.totalProjects) }}</div>
                <div class="stat-label">总项目数</div>
              </div>
            </div>
          </el-tooltip>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <el-tooltip content="今日已完成的自动化扫描次数" placement="top" :show-after="300">
            <div class="stat-card-inner">
              <div class="stat-icon" style="background: #f6ffed; color: #52c41a">
                <el-icon :size="24"><Finished /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ formatCount(stats.todayScans) }}</div>
                <div class="stat-label">今日扫描</div>
              </div>
            </div>
          </el-tooltip>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <el-tooltip content="存在 Critical/Major 风险的分支数" placement="top" :show-after="300">
            <div class="stat-card-inner">
              <div class="stat-icon" style="background: #fff7e6; color: #fa8c16">
                <el-icon :size="24"><WarningFilled /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ formatCount(stats.activeRisks) }}</div>
                <div class="stat-label">活跃风险</div>
              </div>
            </div>
          </el-tooltip>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" class="stat-card">
          <el-tooltip content="各扫描引擎（Trivy/Secrets/IaC）运行状态" placement="top" :show-after="300">
            <div class="stat-card-inner">
              <div class="stat-icon" :style="healthStyle">
                <el-icon :size="24"><Connection /></el-icon>
              </div>
              <div class="stat-info">
                <div class="stat-value">{{ stats.systemStatus }}</div>
                <div class="stat-label">系统状态</div>
              </div>
            </div>
          </el-tooltip>
        </el-card>
      </el-col>
    </el-row>

    <!-- Charts row -->
    <el-row :gutter="16" style="margin-bottom: 20px">
      <el-col :span="16">
        <el-card shadow="hover">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center;">
              <span style="font-weight: 500">扫描趋势</span>
              <el-button size="small" :loading="loading" @click="loadDashboard" circle>
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </template>
          <div style="height: 300px">
            <v-chart :option="trendOption" autoresize style="width: 100%; height: 100%" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header>
            <span style="font-weight: 500">风险等级分布</span>
          </template>
          <div style="height: 250px">
            <v-chart :option="riskOption" autoresize style="width: 100%; height: 100%" />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- Recent activity -->
    <el-card shadow="hover">
      <template #header>
        <span style="font-weight: 500">最近活动</span>
      </template>
      <el-table :data="recentActivities" stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="timestamp" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.timestamp) }}
          </template>
        </el-table-column>
        <el-table-column prop="action" label="操作类型" width="120">
          <template #default="{ row }">
            <el-tag :type="actionTagType(row.action)" size="small">{{ row.action }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resource" label="资源" min-width="200" show-overflow-tooltip />
        <el-table-column prop="user" label="用户" width="120" />
      </el-table>
      <div v-if="!loading && recentActivities.length === 0" style="text-align: center; padding: 20px; color: #909399">
        暂无活动记录
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import 'echarts'
import * as api from '../api'

const loading = ref(false)
const stats = reactive({
  totalProjects: 0,
  todayScans: 0,
  activeRisks: 0,
  systemStatus: '检查中',
})
const healthStyle = computed(() => {
  const v = stats.systemStatus
  if (v === '正常') return { background: '#f6ffed', color: '#52c41a' }
  if (v === '异常') return { background: '#fff2f0', color: '#ff4d4f' }
  return { background: '#f5f5f5', color: '#999' }
})

const recentActivities = ref([])

// ECharts trend option
const trendOption = ref({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, bottom: 30, top: 20 },
  xAxis: {
    type: 'category',
    data: [],
    axisLine: { lineStyle: { color: '#e4e7ed' } },
  },
  yAxis: {
    type: 'value',
    splitLine: { lineStyle: { color: '#f0f2f5' } },
  },
  series: [
    {
      data: [],
      type: 'line',
      smooth: true,
      lineStyle: { width: 3, color: '#409eff' },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(64,158,255,0.3)' },
            { offset: 1, color: 'rgba(64,158,255,0.05)' },
          ],
        },
      },
      itemStyle: { color: '#409eff' },
    },
  ],
})

// ECharts risk distribution option
const riskOption = ref({
  tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
  series: [
    {
      type: 'pie',
      radius: ['40%', '70%'],
      avoidLabelOverlap: false,
      label: { show: true, formatter: '{b}\n{d}%' },
      emphasis: {
        label: { show: true, fontSize: 14, fontWeight: 'bold' },
      },
      data: [
        { value: 0, name: 'CRITICAL', itemStyle: { color: '#f56c6c' } },
        { value: 0, name: 'MAJOR', itemStyle: { color: '#e6a23c' } },
        { value: 0, name: 'MINOR', itemStyle: { color: '#409eff' } },
        { value: 0, name: 'SAFE', itemStyle: { color: '#67c23a' } },
      ],
    },
  ],
})

function formatCount(n) {
  if (n == null || isNaN(n)) return '0'
  const num = Number(n)
  if (num > 9999) return (num / 10000).toFixed(1) + 'w'
  if (num > 999) return '999+'
  return num.toLocaleString()
}

function formatTime(ts) {
  if (!ts) return '-'
  return ts.slice(0, 19).replace('T', ' ')
}

function actionTagType(action) {
  if (!action) return 'info'
  if (action.includes('登录')) return 'success'
  if (action.includes('扫描')) return 'warning'
  if (action.includes('配置')) return 'primary'
  if (action.includes('系统')) return 'danger'
  return 'info'
}

async function loadDashboard() {
  loading.value = true
  try {
    // Load projects
    const projRes = await api.listProjects()
    const projList = Array.isArray(projRes.data) ? projRes.data : projRes.data?.projects || []
    stats.totalProjects = projList.length

    // Load task stats
    try {
      const taskStatsRes = await api.getTaskStats()
      stats.todayScans = taskStatsRes.data?.today_count || taskStatsRes.data?.today || 0
    } catch {
      stats.todayScans = 0
    }

    // Load tasks for risk distribution
    const tasksRes = await api.listTasks(0, 200)
    const tasksList = Array.isArray(tasksRes.data) ? tasksRes.data : tasksRes.data?.items || tasksRes.data?.rows || []

    let critical = 0, major = 0, minor = 0, safe = 0
    let activeRisks = 0
    for (const t of tasksList) {
      const bySev = t.summary?.by_severity || t.result_summary?.by_severity || {}
      critical += bySev.critical || 0
      major += bySev.major || 0
      minor += bySev.minor || 0
      if ((bySev.critical || 0) > 0 || (bySev.major || 0) > 0) activeRisks++
    }
    stats.activeRisks = activeRisks
    safe = Math.max(1, tasksList.length - critical - major - minor)

    riskOption.value.series[0].data = [
      { value: critical, name: 'CRITICAL', itemStyle: { color: '#f56c6c' } },
      { value: major, name: 'MAJOR', itemStyle: { color: '#e6a23c' } },
      { value: minor, name: 'MINOR', itemStyle: { color: '#409eff' } },
      { value: safe, name: 'SAFE', itemStyle: { color: '#67c23a' } },
    ]

    // Load trends
    try {
      const trendsRes = await api.getTrends('daily', 14)
      const trendsData = trendsRes.data
      const items = Array.isArray(trendsData) ? trendsData : trendsData?.data || []
      trendOption.value.xAxis.data = items.map(i => i.date || i.day || i.period || '').filter(Boolean)
      trendOption.value.series[0].data = items.map(i => i.count || i.scan_count || i.total || 0)
    } catch {
      // keep defaults
    }

    // Load recent audit logs
    try {
      const auditRes = await api.listAuditLogs(10)
      const logs = Array.isArray(auditRes.data) ? auditRes.data : auditRes.data?.logs || auditRes.data?.items || []
      recentActivities.value = logs
    } catch {
      recentActivities.value = []
    }

    // Load system health
    try {
      const healthRes = await api.getDeepHealth()
      stats.systemStatus = healthRes.data?.status === 'healthy' || healthRes.data?.status === 'ok' ? '正常' : '异常'
    } catch {
      stats.systemStatus = '异常'
    }
  } catch (e) {
    ElMessage.error('加载仪表盘数据失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

onMounted(loadDashboard)
</script>

<style scoped>
.dashboard-container {
  max-width: 1400px;
  margin: 0 auto;
}
.stat-card {
  border-radius: 8px;
}
.stat-card-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.stat-info {
  flex: 1;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}
.stat-label {
  font-size: 13px;
  color: #909399;
  margin-top: 2px;
}
</style>
