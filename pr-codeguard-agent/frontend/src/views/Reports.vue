<template>
  <div>
    <el-tabs v-model="activeTab">
      <el-tab-pane label="日报" name="daily">
        <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center">
          <el-date-picker
            v-model="reportDate"
            type="date"
            placeholder="选择日期"
            value-format="YYYY-MM-DD"
          />
          <el-button type="primary" @click="loadDailyReport">加载日报</el-button>
          <el-button type="warning" @click="handleSendReport" :loading="sending">
            发送邮件
          </el-button>
        </div>

        <div v-if="dailyReport" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 16px">
          <el-card class="stat-card" shadow="hover">
            <div style="font-size: 13px; color: #909399">合并 MR 数</div>
            <div style="font-size: 28px; font-weight: 700; margin-top: 8px; color: #409eff">
              {{ dailyReport.merge_requests }}
            </div>
          </el-card>
          <el-card class="stat-card" shadow="hover">
            <div style="font-size: 13px; color: #909399">提交数</div>
            <div style="font-size: 28px; font-weight: 700; margin-top: 8px; color: #67c23a">
              {{ dailyReport.commits }}
            </div>
          </el-card>
          <el-card class="stat-card" shadow="hover">
            <div style="font-size: 13px; color: #909399">新增代码行数</div>
            <div style="font-size: 28px; font-weight: 700; margin-top: 8px; color: #e6a23c">
              {{ dailyReport.additions }}
            </div>
          </el-card>
          <el-card class="stat-card" shadow="hover">
            <div style="font-size: 13px; color: #909399">删除代码行数</div>
            <div style="font-size: 28px; font-weight: 700; margin-top: 8px; color: #f56c6c">
              {{ dailyReport.deletions }}
            </div>
          </el-card>
        </div>

        <el-card v-if="dailyReport" shadow="never" style="margin-bottom: 16px">
          <template #header>
            <span>开发者贡献</span>
          </template>
          <el-table :data="dailyReport.contributors" border stripe style="width: 100%">
            <el-table-column prop="developer" label="开发者" />
            <el-table-column prop="commits" label="提交数" width="100" align="center" />
            <el-table-column prop="additions" label="新增行数" width="120" align="center" />
            <el-table-column prop="deletions" label="删除行数" width="120" align="center" />
          </el-table>
        </el-card>

        <el-card v-if="dailyReport" shadow="never">
          <template #header>
            <span>安全问题</span>
          </template>
          <el-table :data="dailyReport.security_findings" border stripe style="width: 100%">
            <el-table-column prop="engine" label="引擎" width="120" />
            <el-table-column prop="severity" label="严重级别" width="120" align="center" />
            <el-table-column prop="file" label="文件" min-width="200" />
            <el-table-column prop="message" label="消息" min-width="300" />
          </el-table>
        </el-card>
      </el-tab-pane>

      <el-tab-pane label="趋势" name="trend">
        <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center">
          <el-radio-group v-model="trendPeriod">
            <el-radio-button value="weekly">每周</el-radio-button>
            <el-radio-button value="monthly">每月</el-radio-button>
          </el-radio-group>
          <span style="font-size: 13px; color: #606266">期数：</span>
          <el-input-number
            v-model="trendCount"
            :min="2"
            :max="52"
            :step="1"
            size="small"
            style="width: 120px"
          />
          <el-button type="primary" @click="loadTrends">加载趋势</el-button>
        </div>

        <el-card shadow="never">
          <VChart :option="chartOption" style="height: 400px" autoresize />
        </el-card>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import * as api from '../api'
import VChart from 'vue-echarts'
import 'echarts'
import { ElMessage } from 'element-plus'

const activeTab = ref('daily')

// === 日报 ===
const reportDate = ref('')
const dailyReport = ref(null)
const sending = ref(false)

const loadDailyReport = async () => {
  try {
    const res = await api.getDailyReport(reportDate.value || '')
    dailyReport.value = res.data
  } catch (e) {
    ElMessage.error('加载日报失败：' + (e.response?.data?.detail || e.message))
  }
}

const handleSendReport = async () => {
  sending.value = true
  try {
    await api.sendReport(reportDate.value || '')
    ElMessage.success('邮件发送成功')
  } catch (e) {
    ElMessage.error('发送失败：' + (e.response?.data?.detail || e.message))
  } finally {
    sending.value = false
  }
}

// === 趋势 ===
const trendPeriod = ref('weekly')
const trendCount = ref(8)
const trendData = ref(null)

const loadTrends = async () => {
  try {
    const res = await api.getTrends(trendPeriod.value, trendCount.value)
    trendData.value = res.data
  } catch (e) {
    ElMessage.error('加载趋势失败：' + (e.response?.data?.detail || e.message))
  }
}

const chartOption = computed(() => {
  if (!trendData.value) return {}
  return {
    tooltip: { trigger: 'axis' },
    legend: {
      data: ['MR 数', '提交数', '新增行数', '安全风险数'],
    },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: trendData.value.periods || [],
    },
    yAxis: { type: 'value' },
    series: [
      {
        name: 'MR 数',
        type: 'line',
        smooth: true,
        data: trendData.value.mr_counts || [],
        itemStyle: { color: '#409eff' },
      },
      {
        name: '提交数',
        type: 'line',
        smooth: true,
        data: trendData.value.commit_counts || [],
        itemStyle: { color: '#67c23a' },
      },
      {
        name: '新增行数',
        type: 'line',
        smooth: true,
        data: trendData.value.addition_counts || [],
        itemStyle: { color: '#e6a23c' },
      },
      {
        name: '安全风险数',
        type: 'line',
        smooth: true,
        data: trendData.value.risk_counts || [],
        itemStyle: { color: '#f56c6c' },
      },
    ],
  }
})
</script>
