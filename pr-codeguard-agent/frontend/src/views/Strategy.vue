<template>
  <div style="padding: 20px">
    <el-tabs v-model="activeTab">
      <!-- ═══════════════════════════════════════════════════════════════
           标签页 1：全局默认策略
           ═══════════════════════════════════════════════════════════════ -->
      <el-tab-pane label="全局默认策略" name="default">
        <el-alert
          title="全局默认策略将应用于所有未单独配置策略的仓库。仓库单独策略的优先级高于全局默认策略。"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 20px"
        />
        <el-form :model="defaultForm" label-width="160px" style="max-width: 560px">
          <el-form-item label="扫描等级">
            <el-select v-model="defaultForm.scan_level">
              <el-option label="Light - 快速扫描 (IaC + Secrets)" value="light" />
              <el-option label="Standard - 标准扫描 (所有引擎)" value="standard" />
              <el-option label="Deep - 深度扫描 (全量 + AI)" value="deep" />
            </el-select>
          </el-form-item>
          <el-form-item label="风险阈值">
            <el-select v-model="defaultForm.risk_threshold">
              <el-option label="Info" value="info" />
              <el-option label="Low" value="low" />
              <el-option label="Medium" value="medium" />
              <el-option label="High" value="high" />
              <el-option label="Critical" value="critical" />
            </el-select>
          </el-form-item>
          <el-form-item label="AI 分析">
            <el-switch v-model="defaultForm.ai_enabled" />
          </el-form-item>
          <el-form-item label="TF 变更检测">
            <el-switch v-model="defaultForm.tf_change_detection" />
          </el-form-item>
          <el-form-item label="自动评论 MR">
            <el-switch v-model="defaultForm.auto_comment" />
          </el-form-item>
          <el-form-item label="评论仅含风险">
            <el-switch v-model="defaultForm.post_comment_only_risks" />
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
              保存全局默认策略
            </el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <!-- ═══════════════════════════════════════════════════════════════
           标签页 2：仓库单独策略
           ═══════════════════════════════════════════════════════════════ -->
      <el-tab-pane label="仓库单独策略" name="repos">
        <el-alert
          title="为特定仓库添加规则，单独配置扫描策略。仓库规则的优先级高于全局默认策略。"
          type="info"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        />
        <div style="margin-bottom: 16px">
          <el-button type="primary" @click="openAddDialog">
            + 添加规则
          </el-button>
        </div>
        <el-table :data="repoList" border stripe style="width: 100%" v-loading="loading">
          <el-table-column type="index" label="#" width="50" />
          <el-table-column prop="repo_url" label="仓库 URL" min-width="220" show-overflow-tooltip />
          <el-table-column prop="scan_level" label="扫描等级" width="100" />
          <el-table-column prop="risk_threshold" label="风险阈值" width="100" />
          <el-table-column prop="ai_enabled" label="AI" width="60">
            <template #default="{ row }">
              <el-tag :type="row.ai_enabled ? 'success' : 'info'" size="small">
                {{ row.ai_enabled ? '开' : '关' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="引擎开关" width="280">
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

    <!-- ═══════════════════════════════════════════════════════════════
         添加 / 编辑仓库策略弹窗
         ═══════════════════════════════════════════════════════════════ -->
    <el-dialog
      v-model="dialogVisible"
      :title="isAddMode ? '添加仓库规则' : '编辑仓库规则'"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-alert
        title="仅配置需要覆盖的字段，未配置的字段将继承全局默认策略。"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-form :model="editForm" label-width="150px">
        <!-- 添加模式：选择仓库 -->
        <el-form-item label="选择仓库" v-if="isAddMode">
          <el-select
            v-model="editForm.repo_url"
            filterable
            remote
            :remote-method="filterProjects"
            :loading="projectLoading"
            placeholder="搜索并选择仓库"
            style="width: 100%"
          >
            <el-option
              v-for="p in filteredProjects"
              :key="p.http_url_to_repo || p.id"
              :label="p.name_with_namespace"
              :value="p.http_url_to_repo"
            >
              <span>{{ p.name_with_namespace }}</span>
              <span style="float: right; color: #909399; font-size: 12px; margin-left: 12px">
                {{ p.http_url_to_repo }}
              </span>
            </el-option>
          </el-select>
        </el-form-item>
        <!-- 编辑模式：显示仓库 URL（不可修改） -->
        <el-form-item label="仓库 URL" v-else>
          <el-input :model-value="editForm.repo_url" disabled />
        </el-form-item>

        <el-form-item label="扫描等级">
          <el-select v-model="editForm.scan_level" placeholder="继承默认" clearable>
            <el-option label="继承默认" value="" />
            <el-option label="Light" value="light" />
            <el-option label="Standard" value="standard" />
            <el-option label="Deep" value="deep" />
          </el-select>
        </el-form-item>
        <el-form-item label="风险阈值">
          <el-select v-model="editForm.risk_threshold" placeholder="继承默认" clearable>
            <el-option label="继承默认" value="" />
            <el-option label="Info" value="info" />
            <el-option label="Low" value="low" />
            <el-option label="Medium" value="medium" />
            <el-option label="High" value="high" />
            <el-option label="Critical" value="critical" />
          </el-select>
        </el-form-item>
        <el-form-item label="AI 分析">
          <el-select v-model="editForm.ai_enabled" placeholder="继承默认" clearable>
            <el-option label="继承默认" value="" />
            <el-option label="开启" :value="true" />
            <el-option label="关闭" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="TF 变更检测">
          <el-select v-model="editForm.tf_change_detection" placeholder="继承默认" clearable>
            <el-option label="继承默认" value="" />
            <el-option label="开启" :value="true" />
            <el-option label="关闭" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="自动评论 MR">
          <el-select v-model="editForm.auto_comment" placeholder="继承默认" clearable>
            <el-option label="继承默认" value="" />
            <el-option label="开启" :value="true" />
            <el-option label="关闭" :value="false" />
          </el-select>
        </el-form-item>
        <el-form-item label="引擎开关">
          <div style="display: flex; flex-direction: column; gap: 8px">
            <div v-for="engine in engineList" :key="engine.key" style="display: flex; align-items: center">
              <el-tag
                :type="getEngineTagType(engine.key)"
                size="small"
                style="cursor: pointer; min-width: 130px"
                @click="cycleEngine(engine.key)"
              >
                {{ getEngineLabel(engine.key) }}
              </el-tag>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleDialogSave" :loading="saving">
          {{ isAddMode ? '添加规则' : '保存修改' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from '../api'

const activeTab = ref('default')
const saving = ref(false)
const loading = ref(false)
const defaultStrategy = ref(null)
const isAddMode = ref(false)
const dialogVisible = ref(false)

const engineList = [
  { key: 'secrets', label: 'Secrets' },
  { key: 'sast', label: 'SAST' },
  { key: 'iac', label: 'IaC' },
  { key: 'best_practice', label: 'Best Practice' },
]

// ─── 全局默认策略 ─────────────────────────────────────────────────

const defaultForm = reactive({
  scan_level: 'standard',
  risk_threshold: 'medium',
  ai_enabled: false,
  tf_change_detection: true,
  auto_comment: true,
  post_comment_only_risks: true,
  engines_enabled: {
    secrets: true,
    sast: true,
    iac: true,
    best_practice: true,
  },
})

const loadDefaultStrategy = async () => {
  try {
    const res = await api.getDefaultStrategy()
    defaultStrategy.value = res.data
    Object.assign(defaultForm, res.data)
  } catch {
    // use defaults
  }
}

const handleSaveDefault = async () => {
  saving.value = true
  try {
    await api.updateDefaultStrategy(defaultForm)
    ElMessage.success('全局默认策略已保存')
    await loadDefaultStrategy()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

// ─── 仓库单独策略列表 ─────────────────────────────────────────────

const repoList = ref([])

const loadRepoList = async () => {
  loading.value = true
  try {
    const res = await api.listStrategies()
    repoList.value = res.data.strategies || res.data
  } catch {
    ElMessage.error('加载仓库策略列表失败')
  } finally {
    loading.value = false
  }
}

const handleDelete = async (repoUrl) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除 "${repoUrl}" 的规则吗？删除后该仓库将自动继承全局默认策略。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await api.deleteRepoStrategy(repoUrl)
    ElMessage.success('规则已删除，该仓库将使用全局默认策略')
    loadRepoList()
  } catch {
    // cancelled or error
  }
}

// ─── 仓库选择器（添加模式） ───────────────────────────────────────

const allProjects = ref([])
const filteredProjects = ref([])
const projectLoading = ref(false)

const loadProjects = async () => {
  try {
    const res = await api.listProjects()
    const projects = Array.isArray(res.data) ? res.data : res.data?.projects || []
    allProjects.value = projects
    // 默认显示全部（过滤掉已有策略的仓库）
    filterProjects('')
  } catch {
    ElMessage.error('加载仓库列表失败')
  }
}

const filterProjects = (query) => {
  const existingUrls = new Set(repoList.value.map(r => r.repo_url))
  const list = allProjects.value.filter(p => {
    const url = p.http_url_to_repo || ''
    if (existingUrls.has(url)) return false
    if (!query) return true
    const q = query.toLowerCase()
    return (p.name_with_namespace || '').toLowerCase().includes(q)
        || url.toLowerCase().includes(q)
  })
  filteredProjects.value = list
}

// ─── 添加 / 编辑弹窗 ─────────────────────────────────────────────

const editForm = reactive({
  repo_url: '',
  scan_level: '',
  risk_threshold: '',
  ai_enabled: '',
  tf_change_detection: '',
  auto_comment: '',
  engines_enabled: {
    secrets: null,
    sast: null,
    iac: null,
    best_practice: null,
  },
})

const resetForm = () => {
  editForm.repo_url = ''
  editForm.scan_level = ''
  editForm.risk_threshold = ''
  editForm.ai_enabled = ''
  editForm.tf_change_detection = ''
  editForm.auto_comment = ''
  editForm.engines_enabled = {
    secrets: null,
    sast: null,
    iac: null,
    best_practice: null,
  }
}

const openAddDialog = async () => {
  isAddMode.value = true
  resetForm()
  await loadProjects()
  dialogVisible.value = true
}

const openEditDialog = async (row) => {
  isAddMode.value = false
  resetForm()
  editForm.repo_url = row.repo_url

  // 加载该仓库已有策略，预填覆盖的字段
  try {
    const res = await api.getRepoStrategy(row.repo_url)
    const existing = res.data
    if (defaultStrategy.value) {
      const def = defaultStrategy.value
      editForm.scan_level = existing.scan_level !== def.scan_level ? existing.scan_level : ''
      editForm.risk_threshold = existing.risk_threshold !== def.risk_threshold ? existing.risk_threshold : ''
      editForm.ai_enabled = existing.ai_enabled !== def.ai_enabled ? existing.ai_enabled : ''
      editForm.tf_change_detection = existing.tf_change_detection !== def.tf_change_detection ? existing.tf_change_detection : ''
      editForm.auto_comment = existing.auto_comment !== def.auto_comment ? existing.auto_comment : ''
      for (const key of Object.keys(editForm.engines_enabled)) {
        if (existing.engines_enabled?.[key] !== def.engines_enabled?.[key]) {
          editForm.engines_enabled[key] = existing.engines_enabled[key]
        }
      }
    }
  } catch {
    // no existing strategy, all inherit default
  }

  dialogVisible.value = true
}

// ─── 引擎开关交互 ────────────────────────────────────────────────

const getEngineTagType = (key) => {
  const val = editForm.engines_enabled[key]
  if (val === null || val === undefined) return 'info'
  return val ? 'success' : 'danger'
}

const getEngineLabel = (key) => {
  const engine = engineList.find(e => e.key === key)
  const name = engine ? engine.label : key
  const val = editForm.engines_enabled[key]
  if (val === null || val === undefined) return `${name} (继承默认)`
  return val ? `${name} (开启)` : `${name} (关闭)`
}

const cycleEngine = (key) => {
  const current = editForm.engines_enabled[key]
  if (current === null || current === undefined) {
    editForm.engines_enabled[key] = true
  } else if (current === true) {
    editForm.engines_enabled[key] = false
  } else {
    editForm.engines_enabled[key] = null
  }
}

// ─── 保存弹窗 ────────────────────────────────────────────────────

const handleDialogSave = async () => {
  if (!editForm.repo_url) {
    ElMessage.warning('请选择仓库')
    return
  }

  saving.value = true
  try {
    // 只发送明确覆盖的字段
    const data = {}
    for (const key of ['scan_level', 'risk_threshold']) {
      if (editForm[key] !== '') {
        data[key] = editForm[key]
      }
    }
    for (const key of ['ai_enabled', 'tf_change_detection', 'auto_comment']) {
      if (editForm[key] !== '') {
        data[key] = editForm[key]
      }
    }
    if (editForm.engines_enabled) {
      const engines = {}
      let hasEngineOverride = false
      for (const [k, v] of Object.entries(editForm.engines_enabled)) {
        if (v !== null) {
          engines[k] = v
          hasEngineOverride = true
        }
      }
      if (hasEngineOverride) {
        data.engines_enabled = engines
      }
    }

    await api.setRepoStrategy(editForm.repo_url, data)
    ElMessage.success(isAddMode.value ? '规则已添加' : '规则已更新')
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
