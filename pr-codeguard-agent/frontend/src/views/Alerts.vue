<template>
  <div>
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <span>告警系统状态</span>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="是否启用" width="150">
          <el-tag :type="status.enabled ? 'success' : 'danger'" size="small">
            {{ status.enabled ? '已启用' : '未启用' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="已配置通道数">
          {{ status.channel_count }}
        </el-descriptions-item>
        <el-descriptions-item label="严重级别阈值">
          <el-tag size="small">{{ status.severity_threshold }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="通道列表">
          <template v-if="status.channels && status.channels.length">
            <el-tag
              v-for="ch in status.channels"
              :key="ch"
              size="small"
              style="margin-right: 6px; margin-bottom: 4px"
            >
              {{ ch }}
            </el-tag>
          </template>
          <span v-else style="color: #909399">无</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <span>测试告警</span>
      </template>
      <el-form label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="testTitle" placeholder="输入告警标题" />
        </el-form-item>
        <el-form-item label="消息">
          <el-input
            v-model="testMessage"
            type="textarea"
            :rows="4"
            placeholder="输入告警消息内容"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleTestAlert" :loading="testing">
            发送测试告警
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <span>发送日报邮件</span>
      </template>
      <div style="display: flex; gap: 12px; align-items: center">
        <el-date-picker
          v-model="reportDate"
          type="date"
          placeholder="选择日期"
          value-format="YYYY-MM-DD"
          style="width: 200px"
        />
        <el-button type="warning" @click="handleSendReport" :loading="sending">
          发送日报邮件
        </el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as api from '../api'
import { ElMessage } from 'element-plus'

const status = ref({
  enabled: false,
  channel_count: 0,
  severity_threshold: '',
  channels: [],
})

const fetchStatus = async () => {
  try {
    const res = await api.getAlertStatus()
    status.value = res.data
  } catch (e) {
    ElMessage.error('获取告警状态失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(fetchStatus)

// === 测试告警 ===
const testTitle = ref('')
const testMessage = ref('')
const testing = ref(false)

const handleTestAlert = async () => {
  if (!testTitle.value || !testMessage.value) {
    ElMessage.warning('请填写标题和消息')
    return
  }
  testing.value = true
  try {
    await api.testAlert(testTitle.value, testMessage.value)
    ElMessage.success('测试告警发送成功')
    testTitle.value = ''
    testMessage.value = ''
  } catch (e) {
    ElMessage.error('发送失败：' + (e.response?.data?.detail || e.message))
  } finally {
    testing.value = false
  }
}

// === 发送日报邮件 ===
const reportDate = ref('')
const sending = ref(false)

const handleSendReport = async () => {
  sending.value = true
  try {
    await api.sendReport(reportDate.value || '')
    ElMessage.success('日报邮件发送成功')
  } catch (e) {
    ElMessage.error('发送失败：' + (e.response?.data?.detail || e.message))
  } finally {
    sending.value = false
  }
}
</script>
