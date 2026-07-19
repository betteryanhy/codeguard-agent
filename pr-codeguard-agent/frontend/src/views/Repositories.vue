<template>
  <div>
    <!-- Top toolbar -->
    <div style="margin-bottom: 16px">
      <el-button type="primary" @click="handleScanDiscovery" :loading="scanning">
        <el-icon><Search /></el-icon>
        扫描发现
      </el-button>
      <el-button type="warning" @click="handleRegisterWebhooks" :loading="registering">
        <el-icon><Link /></el-icon>
        注册 Webhook
      </el-button>
    </div>

    <!-- Projects table -->
    <el-table :data="projects" v-loading="loading" stripe border style="width: 100%">
      <el-table-column prop="name" label="项目名称" min-width="180" />
      <el-table-column prop="namespace" label="命名空间" min-width="180" />
      <el-table-column label="Webhook 状态" width="140">
        <template #default="{ row }">
          <el-tag
            :type="row.webhook_installed ? 'success' : 'danger'"
            effect="plain"
            size="small"
          >
            {{ row.webhook_installed ? '已注册' : '未注册' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button
            type="primary"
            size="small"
            plain
            @click="handleRegisterProjectWebhook(row)"
            :disabled="row.webhook_installed"
          >
            注册 Webhook
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const loading = ref(false)
const scanning = ref(false)
const registering = ref(false)
const projects = ref([])

const fetchProjects = async () => {
  loading.value = true
  try {
    const res = await api.listProjects()
    projects.value = res.data || []
  } catch (e) {
    ElMessage.error('获取项目列表失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

const handleScanDiscovery = async () => {
  scanning.value = true
  try {
    await api.scanDiscovery()
    ElMessage.success('扫描发现完成')
    await fetchProjects()
  } catch (e) {
    ElMessage.error('扫描发现失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    scanning.value = false
  }
}

const handleRegisterWebhooks = async () => {
  registering.value = true
  try {
    await api.registerWebhooks()
    ElMessage.success('Webhook 注册完成')
    await fetchProjects()
  } catch (e) {
    ElMessage.error('批量注册 Webhook 失败: ' + (e.response?.data?.detail || e.message))
  } finally {
    registering.value = false
  }
}

const handleRegisterProjectWebhook = async (row) => {
  try {
    await api.registerProjectWebhook(row.id)
    ElMessage.success(`项目 "${row.name}" Webhook 注册成功`)
    await fetchProjects()
  } catch (e) {
    ElMessage.error('注册 Webhook 失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(fetchProjects)
</script>
