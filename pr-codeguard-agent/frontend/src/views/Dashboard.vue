<template>
  <div class="dashboard-container">
    <!-- 统计卡片行 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-value">{{ statProjects }}</div>
            <div class="stat-label">已发现仓库数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-value">{{ statTasks }}</div>
            <div class="stat-label">扫描任务总数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-value">{{ statCritical }}</div>
            <div class="stat-label">严重发现数</div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never">
          <div class="stat-card">
            <div class="stat-value">{{ statStrategies }}</div>
            <div class="stat-label">已配置策略数</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 趋势图与风险分布 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>
            <span>扫描趋势（近 8 周）</span>
          </template>
          <VChart :option="trendsOption" autoresize style="height: 350px" />
        </el-card>
      </el-col>
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            <span>发现级别分布</span>
          </template>
          <VChart :option="pieOption" autoresize style="height: 350px" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 近日任务列表 -->
    <el-card shadow="never" class="table-card">
      <template #header>
        <span>近日扫描任务</span>
      </template>
      <el-table :data="recentTasks" style="width: 100%" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="repo_url" label="仓库地址" min-width="200" show-overflow-tooltip />
        <el-table-column prop="status" label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="100" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="viewTask(row.id)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import 'echarts'
import * as api from '../api'

const router = useRouter()

// 统计卡片数据
const statProjects = ref(0)
const statTasks = ref(0)
const statCritical = ref(0)
const statStrategies = ref(0)

// 图表配置项
const trendsOption = ref({})
const pieOption = ref({})

// 近日任务
const recentTasks = ref([])

function statusTag(status) {
  const map = {
    completed: 'success',
    running: 'warning',
    pending: 'info',
    failed: 'danger',
  }
  return map[status] || 'info'
}

function viewTask(id) {
  router.push(`/tasks/${id}`)
}

onMounted(async () => {
  try {
    const [projectsRes, tasksRes, trendsRes, , strategiesRes] = await Promise.all([
      api.listProjects(),
      api.listTasks(0, 5),
      api.getTrends('weekly', 8),
      api.getDefaultStrategy(),
      api.listStrategies(),
    ])

    // 仓库数
    const projects = projectsRes.data
    statProjects.value = Array.isArray(projects) ? projects.length : projects?.total || 0

    // 任务总数 & 近 5 条
    const tasksData = tasksRes.data
    if (tasksData.total !== undefined) {
      statTasks.value = tasksData.total
      recentTasks.value = tasksData.items || tasksData.rows || []
    } else if (Array.isArray(tasksData)) {
      statTasks.value = tasksData.length
      recentTasks.value = tasksData
    }

    // 策略数
    const strategies = strategiesRes.data
    if (Array.isArray(strategies)) {
      statStrategies.value = strategies.length
    } else {
      statStrategies.value = strategies?.items?.length || strategies?.rows?.length || 0
    }

    // 趋势数据
    const trends = Array.isArray(trendsRes.data)
      ? trendsRes.data
      : trendsRes.data?.items || []

    const weeks = trends.map((t) => t.period || t.week || t.date || '')
    const totalFindings = trends.map((t) => t.total || t.count || 0)
    const critical = trends.map((t) => t.critical || 0)
    const high = trends.map((t) => t.high || 0)
    const medium = trends.map((t) => t.medium || 0)
    const low = trends.map((t) => t.low || 0)

    // 取最近一周的严重发现数
    if (critical.length > 0) {
      statCritical.value = critical[critical.length - 1]
    }

    // 折线图
    trendsOption.value = {
      tooltip: { trigger: 'axis' },
      legend: { data: ['严重', '高危', '中危', '低危', '总发现数'] },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: weeks, boundaryGap: false },
      yAxis: { type: 'value' },
      series: [
        { name: '严重', type: 'line', data: critical, smooth: true, lineStyle: { width: 2 } },
        { name: '高危', type: 'line', data: high, smooth: true, lineStyle: { width: 2 } },
        { name: '中危', type: 'line', data: medium, smooth: true, lineStyle: { width: 2 } },
        { name: '低危', type: 'line', data: low, smooth: true, lineStyle: { width: 2 } },
        { name: '总发现数', type: 'line', data: totalFindings, smooth: true, lineStyle: { width: 2 } },
      ],
    }

    // 饼图 - 使用最近一周的级别数据
    const latest = trends.length > 0 ? trends[trends.length - 1] : null
    const pieData = latest
      ? [
          { name: '严重', value: latest.critical || 0 },
          { name: '高危', value: latest.high || 0 },
          { name: '中危', value: latest.medium || 0 },
          { name: '低危', value: latest.low || 0 },
        ].filter((d) => d.value > 0)
      : []

    if (pieData.length === 0) {
      pieData.push({ name: '暂无数据', value: 1 })
    }

    pieOption.value = {
      tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
      legend: { bottom: '0%' },
      series: [
        {
          type: 'pie',
          radius: ['40%', '65%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: false,
          label: { show: false },
          emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
          data: pieData,
        },
      ],
    }
  } catch (e) {
    ElMessage.error('加载仪表盘数据失败: ' + (e.message || '未知错误'))
  }
})
</script>

<style scoped>
.dashboard-container {
  background: transparent;
}

.stat-row {
  margin-bottom: 16px;
}

.stat-card {
  text-align: center;
  padding: 8px 0;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.stat-label {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
}

.chart-row {
  margin-bottom: 16px;
}

.table-card {
  margin-bottom: 16px;
}
</style>
