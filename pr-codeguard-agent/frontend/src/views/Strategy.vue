<template>
  <div style="padding: 20px">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="默认策略" name="default">
        <el-form :model="defaultForm" label-width="160px" style="max-width: 560px">
          <el-form-item label="扫描等级">
            <el-select v-model="defaultForm.scan_level">
              <el-option label="Light" value="light" />
              <el-option label="Standard" value="standard" />
              <el-option label="Deep" value="deep" />
            </el-select>
          </el-form-item>
          <el-form-item label="风险阈值">
            <el-select v-model="defaultForm.risk_threshold">
              <el-option label="Info" value="info" />
              <el-option label="Minor" value="minor" />
              <el-option label="Major" value="major" />
              <el-option label="Critical" value="critical" />
              <el-option label="Blocker" value="blocker" />
            </el-select>
          </el-form-item>
          <el-form-item label="AI 分析">
            <el-switch v-model="defaultForm.ai_enabled" />
          </el-form-item>
          <el-form-item label="TF 变更检测">
            <el-switch v-model="defaultForm.tf_change_detection" />
          </el-form-item>
          <el-form-item label="自动评论">
            <el-switch v-model="defaultForm.auto_comment" />
          </el-form-item>
          <el-form-item label="引擎开关">
            <div style="display: flex; flex-direction: column; gap: 8px">
              <el-checkbox v-model="defaultForm.engines_enabled.secrets" label="Secrets" />
              <el-checkbox v-model="defaultForm.engines_enabled.sast" label="SAST" />
              <el-checkbox v-model="defaultForm.engines_enabled.iac" label="IaC" />
              <el-checkbox v-model="defaultForm.engines_enabled.best_practice" label="Best Practice" />
            </div>
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="handleSaveDefault" :loading="saving">
              保存
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="仓库策略列表" name="repos">
        <el-table :data="repoList" border stripe style="width: 100%">
          <el-table-column prop="repo_url" label="仓库 URL" min-width="200" />
          <el-table-column prop="scan_level" label="扫描等级" width="120" />
          <el-table-column prop="risk_threshold" label="风险阈值" width="120" />
          <el-table-column label="引擎开关" width="240">
            <template #default="{ row }">
              <el-tag
                v-for="(v, k) in row.engines_enabled"
                :key="k"
                :type="v ? 'success' : 'info'"
                size="small"
                style="margin-right: 4px"
              >
                {{ k }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="handleDelete(row.repo_url)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialogVisible" title="编辑仓库策略" width="500px">
      <el-form :model="editForm" label-width="140px">
        <el-form-item label="仓库 URL">
          <el-input :model-value="editForm.repo_url" disabled />
        </el-form-item>
        <el-form-item label="扫描等级">
          <el-select v-model="editForm.scan_level">
            <el-option label="Light" value="light" />
            <el-option label="Standard" value="standard" />
            <el-option label="Deep" value="deep" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险阈值">
          <el-select v-model="editForm.risk_threshold">
            <el-option label="Info" value="info" />
            <el-option label="Minor" value="minor" />
            <el-option label="Major" value="major" />
            <el-option label="Critical" value="critical" />
            <el-option label="Blocker" value="blocker" />
          </el-select>
        </el-form-item>
        <el-form-item label="AI 分析">
          <el-switch v-model="editForm.ai_enabled" />
        </el-form-item>
        <el-form-item label="TF 变更检测">
          <el-switch v-model="editForm.tf_change_detection" />
        </el-form-item>
        <el-form-item label="自动评论">
          <el-switch v-model="editForm.auto_comment" />
        </el-form-item>
        <el-form-item label="引擎开关">
          <div style="display: flex; flex-direction: column; gap: 8px">
            <el-checkbox v-model="editForm.engines_enabled.secrets" label="Secrets" />
            <el-checkbox v-model="editForm.engines_enabled.sast" label="SAST" />
            <el-checkbox v-model="editForm.engines_enabled.iac" label="IaC" />
            <el-checkbox v-model="editForm.engines_enabled.best_practice" label="Best Practice" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleEditSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../api'

const activeTab = ref('default')
const saving = ref(false)

// --- Default strategy ---
const defaultForm = reactive({
  scan_level: 'standard',
  risk_threshold: 'major',
  ai_enabled: true,
  tf_change_detection: false,
  auto_comment: false,
  engines_enabled: {
    secrets: true,
    sast: true,
    iac: false,
    best_practice: true,
  },
})

const loadDefaultStrategy = async () => {
  try {
    const res = await api.getDefaultStrategy()
    Object.assign(defaultForm, res.data)
  } catch {
    // use defaults
  }
}

const handleSaveDefault = async () => {
  saving.value = true
  try {
    await api.updateDefaultStrategy(defaultForm)
    ElMessage.success('默认策略已保存')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

// --- Repo strategies ---
const repoList = ref([])

const loadRepoList = async () => {
  try {
    const res = await api.listStrategies()
    repoList.value = res.data
  } catch {
    ElMessage.error('加载仓库策略列表失败')
  }
}

const handleDelete = async (repoUrl) => {
  try {
    await ElMessageBox.confirm('确定要删除该仓库的策略吗？', '确认', { type: 'warning' })
    await api.deleteRepoStrategy(repoUrl)
    ElMessage.success('已删除')
    loadRepoList()
  } catch {
    // cancelled or error
  }
}

// --- Edit dialog ---
const dialogVisible = ref(false)
const editForm = reactive({
  repo_url: '',
  scan_level: 'standard',
  risk_threshold: 'major',
  ai_enabled: true,
  tf_change_detection: false,
  auto_comment: false,
  engines_enabled: {
    secrets: true,
    sast: true,
    iac: false,
    best_practice: true,
  },
})

const openEditDialog = (row) => {
  editForm.repo_url = row.repo_url
  editForm.scan_level = row.scan_level
  editForm.risk_threshold = row.risk_threshold
  editForm.ai_enabled = row.ai_enabled
  editForm.tf_change_detection = row.tf_change_detection
  editForm.auto_comment = row.auto_comment
  if (row.engines_enabled) {
    editForm.engines_enabled = { ...row.engines_enabled }
  }
  dialogVisible.value = true
}

const handleEditSave = async () => {
  saving.value = true
  try {
    const { repo_url, ...data } = editForm
    await api.setRepoStrategy(repo_url, data)
    ElMessage.success('仓库策略已保存')
    dialogVisible.value = false
    loadRepoList()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadDefaultStrategy()
  loadRepoList()
})
</script>
