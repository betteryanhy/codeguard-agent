<template>
  <div class="settings-container">
    <el-card shadow="hover">
      <el-tabs v-model="activeTab">
        <!-- General -->
        <el-tab-pane label="常规" name="general">
          <el-form :model="settings" label-width="160px" style="max-width: 500px">
            <el-form-item label="自动扫描">
              <el-switch v-model="settings.auto_scan" />
              <span style="margin-left: 12px; font-size: 13px; color: #909399">
                {{ settings.auto_scan ? '开启' : '关闭' }}
              </span>
            </el-form-item>
            <el-form-item label="扫描时间">
              <el-time-picker
                v-model="settings.scan_time"
                :disabled="!settings.auto_scan"
                placeholder="选择扫描时间"
                format="HH:mm"
                style="width: 180px"
              />
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Alert -->
        <el-tab-pane label="告警" name="alert">
          <el-form :model="settings" label-width="160px" style="max-width: 500px">
            <el-form-item label="风险阈值">
              <el-select v-model="settings.alert_threshold" style="width: 180px">
                <el-option label="仅 Critical" value="critical" />
                <el-option label="Critical + Major" value="major" />
                <el-option label="全部" value="all" />
              </el-select>
            </el-form-item>
            <el-form-item label="通道状态">
              <div style="display: flex; gap: 16px">
                <el-tag v-if="settings.alert_channels?.email" type="success" effect="plain">邮件 已配置</el-tag>
                <el-tag v-else type="info" effect="plain">邮件 未配置</el-tag>
                <el-tag v-if="settings.alert_channels?.webhook" type="success" effect="plain">Webhook 已配置</el-tag>
                <el-tag v-else type="info" effect="plain">Webhook 未配置</el-tag>
              </div>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- Engines -->
        <el-tab-pane label="引擎" name="engines">
          <el-form label-width="160px" style="max-width: 500px">
            <el-form-item v-for="engine in engineList" :key="engine.key" :label="engine.label">
              <el-switch v-model="settings.engines[engine.key]" />
              <span style="margin-left: 12px; font-size: 13px; color: #909399">
                {{ settings.engines[engine.key] ? '已启用' : '已禁用' }}
              </span>
            </el-form-item>
          </el-form>
        </el-tab-pane>

        <!-- GitLab -->
        <el-tab-pane label="GitLab" name="gitlab">
          <el-form :model="settings" label-width="160px" style="max-width: 500px">
            <el-form-item label="连接状态">
              <div style="display: flex; align-items: center; gap: 8px">
                <span :style="{ width: 10, height: 10, borderRadius: '50%', display: 'inline-block', background: settings.gitlab_connected ? '#67c23a' : '#f56c6c' }"></span>
                <span>{{ settings.gitlab_connected ? '已连接' : '未连接' }}</span>
              </div>
            </el-form-item>
            <el-form-item label="GitLab URL">
              <el-input :model-value="settings.gitlab_url" disabled placeholder="未配置" />
            </el-form-item>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e4e7ed">
        <el-button type="primary" :loading="saving" @click="handleSave">保存设置</el-button>
        <el-button @click="loadSettings">重置</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const activeTab = ref('general')
const saving = ref(false)

const engineList = [
  { key: 'secrets', label: 'Secrets（密钥检测）' },
  { key: 'sast', label: 'SAST（静态分析）' },
  { key: 'iac', label: 'IaC（基础设施即代码）' },
  { key: 'best_practice', label: 'Best Practice（最佳实践）' },
]

const settings = reactive({
  auto_scan: false,
  scan_time: null,
  alert_threshold: 'major',
  alert_channels: { email: false, webhook: false },
  engines: {
    secrets: true,
    sast: true,
    iac: true,
    best_practice: true,
  },
  gitlab_connected: false,
  gitlab_url: '',
})

async function loadSettings() {
  try {
    const res = await api.getSystemSettings()
    const data = res.data?.settings || res.data
    if (data) {
      Object.assign(settings, data)
    }
  } catch {
    // use defaults
  }
}

async function handleSave() {
  saving.value = true
  try {
    await api.updateSystemSettings({ ...settings })
    ElMessage.success('设置已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

onMounted(loadSettings)
</script>

<style scoped>
.settings-container {
  max-width: 800px;
  margin: 0 auto;
}
</style>
