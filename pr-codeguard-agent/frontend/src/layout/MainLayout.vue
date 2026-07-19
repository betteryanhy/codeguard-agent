<template>
  <el-container style="min-height: 100vh">
    <!-- Sidebar -->
    <el-aside :width="isCollapse ? '64px' : '220px'" style="background: #fff; border-right: 1px solid #e6e6e6; transition: width 0.3s">
      <div class="sidebar-logo">
        <el-icon :size="24"><Shield /></el-icon>
        <span v-show="!isCollapse">CodeGuard</span>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="isCollapse"
        :router="true"
        style="border-right: none"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <template #title>概览</template>
        </el-menu-item>
        <el-menu-item index="/repositories">
          <el-icon><FolderOpened /></el-icon>
          <template #title>仓库列表</template>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <template #title>扫描任务</template>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Setting /></el-icon>
          <template #title>扫描策略</template>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><Search /></el-icon>
          <template #title>知识库搜索</template>
        </el-menu-item>
        <el-menu-item index="/reports">
          <el-icon><DataAnalysis /></el-icon>
          <template #title>日报 & 趋势</template>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <el-icon><WarningFilled /></el-icon>
          <template #title>告警系统</template>
        </el-menu-item>
        <el-menu-item index="/chat" style="margin-top: 4px; border-top: 1px solid #f0f0f0">
          <el-icon><ChatDotRound /></el-icon>
          <template #title>Agent 对话</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- Main -->
    <el-container>
      <el-header style="height: 50px; background: #fff; border-bottom: 1px solid #e6e6e6; display: flex; align-items: center; justify-content: space-between; padding: 0 20px">
        <div style="display: flex; align-items: center">
          <el-button :icon="isCollapse ? 'Expand' : 'Fold'" text @click="isCollapse = !isCollapse" />
          <el-breadcrumb separator="/" style="margin-left: 16px">
            <el-breadcrumb-item :to="{ path: '/dashboard' }">CodeGuard</el-breadcrumb-item>
            <el-breadcrumb-item v-if="route.meta.title">{{ route.meta.title }}</el-breadcrumb-item>
          </el-breadcrumb>
        </div>
        <div>
          <el-tag type="success" size="small" effect="plain">运行中</el-tag>
        </div>
      </el-header>

      <el-main style="padding: 20px; background: #f5f7fa">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isCollapse = ref(false)
</script>
