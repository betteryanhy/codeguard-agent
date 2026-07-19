<template>
  <div style="padding: 20px">
    <!-- Search area -->
    <el-card shadow="never" style="margin-bottom: 20px">
      <el-form :inline="true" :model="searchForm">
        <el-form-item label="关键词" style="margin-bottom: 0">
          <el-input v-model="searchForm.q" placeholder="输入搜索关键词" clearable style="width: 300px" @keyup.enter="handleSearch" />
        </el-form-item>
        <el-form-item label="搜索范围" style="margin-bottom: 0">
          <el-select v-model="searchForm.scope" style="width: 140px">
            <el-option label="全部" value="all" />
            <el-option label="代码" value="code" />
            <el-option label="MR" value="mr" />
          </el-select>
        </el-form-item>
        <el-form-item style="margin-bottom: 0">
          <el-button type="primary" @click="handleSearch" :loading="searching">搜索</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Search results -->
    <template v-if="searchResults.length > 0">
      <el-row :gutter="16">
        <el-col :span="12" v-for="item in searchResults" :key="item.id || item.content" style="margin-bottom: 16px">
          <el-card shadow="hover">
            <div style="margin-bottom: 12px">
              <span v-for="(seg, idx) in highlightSegments(item.content)" :key="idx">
                <span v-if="seg.highlight" style="color: #e6a23c; font-weight: 600; background: #fdf6ec">{{ seg.text }}</span>
                <span v-else>{{ seg.text }}</span>
              </span>
            </div>
            <el-progress
              :percentage="Math.round((item.score || 0) * 100)"
              :status="item.score >= 0.7 ? 'success' : item.score >= 0.4 ? 'warning' : 'exception'"
              :stroke-width="8"
              style="margin-bottom: 8px"
            />
            <div style="display: flex; justify-content: space-between; font-size: 12px; color: #909399">
              <span>{{ item.repo_url }}</span>
              <el-tag size="small">{{ item.scope }}</el-tag>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>
    <el-empty v-else-if="searched && searchResults.length === 0" description="未找到相关结果" />

    <!-- Recent MR knowledge records -->
    <el-card shadow="never" style="margin-top: 24px">
      <template #header>
        <span>最近的 MR 知识记录</span>
      </template>
      <el-table :data="mrList" border stripe style="width: 100%">
        <el-table-column prop="title" label="MR 标题" min-width="200" />
        <el-table-column prop="repo_url" label="仓库 URL" min-width="200" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const searchForm = reactive({
  q: '',
  scope: 'all',
})
const searchResults = ref([])
const searched = ref(false)
const searching = ref(false)

const handleSearch = async () => {
  if (!searchForm.q.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searched.value = true
  searching.value = true
  try {
    const res = await api.searchKnowledge(searchForm.q.trim(), searchForm.scope)
    searchResults.value = res.data?.results || res.data || []
  } catch (e) {
    ElMessage.error('搜索失败: ' + (e.response?.data?.detail || e.message))
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

const highlightSegments = (text) => {
  if (!text || !searchForm.q.trim()) return [{ text: text || '', highlight: false }]
  const q = searchForm.q.trim()
  const regex = new RegExp(`(${q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
  const parts = text.split(regex)
  return parts.map((part) => ({
    text: part,
    highlight: regex.test(part),
  }))
}

// Recent MR records
const mrList = ref([])

const loadMrList = async () => {
  try {
    const res = await api.listKnowledgeMrs()
    mrList.value = res.data?.results || res.data || []
  } catch {
    // silently fail
  }
}

onMounted(() => {
  loadMrList()
})
</script>
