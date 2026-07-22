<template>
  <div class="risk-root">
    <!-- Search & filter bar -->
    <div class="risk-toolbar">
      <div class="toolbar-left">
        <el-input
          v-model="searchQuery"
          placeholder="搜索项目名..."
          clearable
          class="search-input"
          :prefix-icon="'Search'"
        />
        <el-checkbox v-model="onlyRisky" class="filter-risky">仅显示有风险的项目</el-checkbox>
      </div>
      <el-button text size="small" @click="loadData">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <!-- Empty state -->
    <div v-if="filteredProjects.length === 0 && !loading" class="risk-empty">
      暂无项目数据
    </div>

    <!-- Project list -->
    <div v-loading="loading" class="risk-list">
      <div
        v-for="proj in filteredProjects"
        :key="proj.id || proj.http_url_to_repo"
        class="project-entry"
      >
        <!-- Project header row -->
        <div class="project-head" @click="toggleProject(proj)">
          <svg class="folder-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span class="project-label">{{ proj.name_with_namespace || proj.http_url_to_repo }}</span>
          <span :class="['level-badge', proj.level || 'safe']">
            {{ levelLabel(proj.level) }}
          </span>
          <span class="finding-count" v-if="proj.totalFindings !== undefined">
            {{ proj.totalFindings }} 发现
          </span>
          <span class="pending-badge" v-if="proj.pendingCount > 0">
            {{ proj.pendingCount }} 待扫描
          </span>
          <el-button
            size="small"
            plain
            class="scan-btn"
            :loading="scanningProjects[proj.http_url_to_repo || proj.id]"
            @click.stop="triggerScan(proj)"
          >
            扫描
          </el-button>
          <svg
            :class="['chevron', { open: expandedProjects.has(proj) }]"
            width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          >
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </div>

        <!-- Expanded branches section -->
        <div v-if="expandedProjects.has(proj)" class="branches-wrap">
          <div
            v-for="branch in proj.branches"
            :key="branch.task_id || branch.name"
            class="branch-row"
          >
            <div class="branch-head" @click="toggleBranch(branch)">
              <span class="branch-name">{{ branch.name || 'main' }}</span>
              <span class="branch-meta">{{ branch.default ? '默认' : '' }}</span>
              <span :class="['level-badge small', branch.level || 'safe']">
                {{ levelLabel(branch.level) }}
              </span>
              <span class="branch-findings" v-if="branch.findingCount !== undefined">
                {{ branch.findingCount }} 发现
              </span>
              <span class="branch-time">{{ branch.scanTime }}</span>
              <svg
                :class="['chevron small', { open: expandedBranches.has(branch.task_id) }]"
                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
              >
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>

            <!-- Inline findings panel -->
            <div v-if="expandedBranches.has(branch.task_id)" class="findings-panel">
              <div class="scan-meta">
                <span>扫描引擎: {{ branch.engines || '-' }}</span>
                <span>耗时: {{ branch.duration || '-' }}</span>
              </div>

              <div v-if="branch.findings && branch.findings.length > 0" class="findings-list">
                <div v-for="(f, fi) in branch.findings" :key="fi" class="finding-card">
                  <div class="finding-head">
                    <span :class="['sev-tag', f.severity ? f.severity.toLowerCase() : 'info']">
                      {{ (f.severity || 'INFO').toUpperCase() }}
                    </span>
                    <span class="finding-engine">{{ f.engine }}</span>
                  </div>
                  <div class="finding-msg">{{ f.message }}</div>
                  <div class="finding-loc" v-if="f.file_path">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    <code>{{ f.file_path }}{{ f.line ? ':' + f.line : '' }}</code>
                  </div>
                </div>
              </div>
              <div v-else class="findings-empty">暂无发现</div>
            </div>
          </div>

          <!-- Pending tasks summary -->
          <div v-if="proj._pendingTasks && proj._pendingTasks.length > 0" class="pending-summary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
            {{ proj._pendingTasks.length }} 个待扫描任务（需在 GitLab 创建 MR 触发，或点击「扫描」按钮手动扫描）
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import * as api from '../api'

const searchQuery = ref('')
const onlyRisky = ref(false)
const loading = ref(false)
const projects = ref([])
const expandedProjects = ref(new Set())
const expandedBranches = ref(new Set())
const scanningProjects = reactive({})

function levelLabel(level) {
  const map = { critical: '高危', major: '中危', minor: '低危', safe: '安全' }
  return map[level] || '安全'
}

async function triggerScan(proj) {
  const repoUrl = proj.http_url_to_repo || ''
  if (!repoUrl) { ElMessage.warning('无法获取仓库地址'); return }
  const key = repoUrl || proj.id
  scanningProjects[key] = true
  try {
    const res = await api.scanRepo(repoUrl, proj.default_branch || 'main')
    ElMessage.success(`扫描完成: ${res.data.findings_count} 个发现`)
    await loadData()
  } catch (e) {
    ElMessage.error('扫描失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    scanningProjects[key] = false
  }
}

function toggleProject(proj) {
  const s = expandedProjects.value
  s.has(proj) ? s.delete(proj) : s.add(proj)
}

function toggleBranch(branch) {
  const s = expandedBranches.value
  if (s.has(branch.task_id)) {
    s.delete(branch.task_id)
  } else {
    s.add(branch.task_id)
    if (!branch.findings && !branch._loaded) {
      branch._loaded = true
      loadBranchFindings(branch)
    }
  }
}

async function loadBranchFindings(branch) {
  try {
    const res = await api.getResult(branch.task_id)
    const data = res.data
    branch.findings = data.findings || data.results || []
    branch.engines = branch.engines || (data.summary ? 'trivy' : '-')
  } catch {
    branch.findings = []
  }
}

function processBranches(proj, tasks) {
  // Split completed vs pending
  const completed = tasks.filter(t => t.status === 'completed')
  const pending = tasks.filter(t => t.status === 'pending' || t.status === 'failed')

  proj._pendingTasks = pending

  // Group completed tasks by branch name, keep latest
  const branchMap = {}
  for (const t of completed) {
    const branchName = t.branch_name || 'main'
    if (!branchMap[branchName] || (t.created_at || '') > (branchMap[branchName].created_at || '')) {
      branchMap[branchName] = t
    }
  }

  const branches = Object.entries(branchMap).map(([name, task]) => {
    const bySev = task.summary?.by_severity || {}
    let level = 'safe'
    if ((bySev.critical || 0) > 0) level = 'critical'
    else if ((bySev.major || 0) > 0) level = 'major'
    else if ((bySev.minor || 0) > 0) level = 'minor'

    const findingCount = (bySev.critical || 0) + (bySev.major || 0) + (bySev.minor || 0)
    const scanTime = task.created_at ? task.created_at.slice(0, 10) : ''

    return {
      name,
      task_id: task.id,
      level,
      findingCount,
      scanTime,
      findings: null, // lazy-loaded
      default: name === (proj.default_branch || 'main'),
      engines: task.engines || '',
      duration: task.duration || '',
    }
  })

  // Sort: default branch first, then by name
  branches.sort((a, b) => {
    if (a.default) return -1
    if (b.default) return 1
    return a.name.localeCompare(b.name)
  })

  return branches
}

function computeProjectRisk(proj) {
  let totalFindings = 0
  let maxLevel = 'safe'
  for (const b of (proj.branches || [])) {
    // Count from the by_severity of the task
    const task = proj._allTasks?.find(t => t.id === b.task_id)
    if (task?.summary?.by_severity) {
      const bs = task.summary.by_severity
      totalFindings += (bs.critical || 0) + (bs.major || 0) + (bs.minor || 0)
      if ((bs.critical || 0) > 0) maxLevel = 'critical'
      else if ((bs.major || 0) > 0 && maxLevel !== 'critical') maxLevel = 'major'
      else if ((bs.minor || 0) > 0 && maxLevel === 'safe') maxLevel = 'minor'
    }
  }
  proj.totalFindings = totalFindings
  proj.level = maxLevel
}

const filteredProjects = computed(() => {
  let list = projects.value
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(p => (p.name_with_namespace || '').toLowerCase().includes(q))
  }
  if (onlyRisky.value) {
    list = list.filter(p => p.level && p.level !== 'safe')
  }
  return list
})

async function loadData() {
  loading.value = true
  try {
    const projRes = await api.listProjects()
    const projList = Array.isArray(projRes.data) ? projRes.data : projRes.data?.projects || []

    const tasksRes = await api.listTasks(0, 200)
    const tasksList = Array.isArray(tasksRes.data) ? tasksRes.data : tasksRes.data?.items || tasksRes.data?.rows || []

    for (const proj of projList) {
      const repoUrl = (proj.http_url_to_repo || '').replace(/\.git$/, '')
      const projTasks = tasksList.filter(t => (t.repo_url || '').replace(/\.git$/, '') === repoUrl)

      // Normalize summary
      for (const t of projTasks) {
        t.summary = t.summary || t.result_summary || null
      }

      proj._allTasks = projTasks
      proj.pendingCount = projTasks.filter(t => t.status === 'pending').length
      proj.branches = processBranches(proj, projTasks)
      computeProjectRisk(proj)
    }

    projects.value = projList
  } catch (e) {
    ElMessage.error('加载数据失败: ' + (e.message || '未知错误'))
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<style scoped>
.risk-root {
  max-width: 1000px;
  margin: 0 auto;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
}

/* Toolbar */
.risk-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
}
.search-input {
  width: 280px;
}
.filter-risky {
  white-space: nowrap;
  font-size: 13px;
}

/* Empty */
.risk-empty {
  text-align: center;
  padding: 60px 0;
  color: #909399;
  font-size: 14px;
}

/* Project entry */
.risk-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.project-entry {
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 10px;
  overflow: hidden;
  transition: box-shadow 0.15s;
}
.project-entry:hover {
  box-shadow: 0 1px 4px rgba(0,0,0,0.04);
}

/* Project header */
.project-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  cursor: pointer;
  user-select: none;
  transition: background 0.1s;
}
.project-head:hover {
  background: #f8f9fb;
}
.folder-icon {
  color: #5f6368;
  flex-shrink: 0;
}
.project-label {
  font-size: 14px;
  font-weight: 500;
  color: #202124;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Level badges */
.level-badge {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 20px;
  white-space: nowrap;
  flex-shrink: 0;
}
.level-badge.safe { background: #e6f4ea; color: #1e8e3e; }
.level-badge.minor { background: #fef7e0; color: #ea8600; }
.level-badge.major { background: #fce8e6; color: #d93025; }
.level-badge.critical { background: #fce8e6; color: #c5221f; }

.level-badge.small { font-size: 10px; padding: 1px 8px; }

/* Finding count */
.finding-count {
  font-size: 12px;
  color: #5f6368;
  white-space: nowrap;
}

/* Pending badge */
.pending-badge {
  font-size: 11px;
  color: #80868b;
  background: #f1f3f4;
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}

/* Scan button */
.scan-btn {
  font-size: 12px !important;
  padding: 4px 12px !important;
  height: auto !important;
  flex-shrink: 0;
}

/* Chevron */
.chevron {
  color: #9aa0a6;
  transition: transform 0.2s;
  flex-shrink: 0;
}
.chevron.open {
  transform: rotate(90deg);
}
.chevron.small {
  margin-left: auto;
}

/* Branches */
.branches-wrap {
  border-top: 1px solid #e8eaed;
}
.branch-row {
  border-bottom: 1px solid #f1f3f4;
}
.branch-row:last-child {
  border-bottom: none;
}

.branch-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px 10px 48px;
  cursor: pointer;
  transition: background 0.1s;
}
.branch-head:hover {
  background: #f8f9fb;
}

.branch-name {
  font-size: 13px;
  color: #202124;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}
.branch-meta {
  font-size: 11px;
  color: #80868b;
  background: #f1f3f4;
  padding: 0 6px;
  border-radius: 4px;
}
.branch-findings {
  font-size: 12px;
  color: #5f6368;
}
.branch-time {
  font-size: 11px;
  color: #9aa0a6;
  margin-left: auto;
}

/* Findings panel */
.findings-panel {
  padding: 0 18px 14px 48px;
  background: #fafbfc;
}
.scan-meta {
  display: flex;
  gap: 20px;
  font-size: 11px;
  color: #9aa0a6;
  padding: 10px 0;
  border-bottom: 1px solid #e8eaed;
  margin-bottom: 10px;
}

.findings-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.finding-card {
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 8px;
  padding: 10px 14px;
}
.finding-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.sev-tag {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  letter-spacing: 0.02em;
}
.sev-tag.critical { background: #fce8e6; color: #c5221f; }
.sev-tag.major { background: #fce8e6; color: #d93025; }
.sev-tag.minor { background: #fef7e0; color: #ea8600; }
.sev-tag.info { background: #e8f0fe; color: #1a73e8; }

.finding-engine {
  font-size: 11px;
  color: #9aa0a6;
}
.finding-msg {
  font-size: 13px;
  color: #202124;
  line-height: 1.45;
}
.finding-loc {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
  font-size: 11px;
  color: #80868b;
}
.finding-loc code {
  background: #f1f3f4;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
}
.findings-empty {
  text-align: center;
  color: #9aa0a6;
  padding: 14px 0;
  font-size: 13px;
}

/* Pending summary */
.pending-summary {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 18px 10px 48px;
  font-size: 12px;
  color: #80868b;
  background: #fafbfc;
  border-top: 1px solid #e8eaed;
}
</style>
