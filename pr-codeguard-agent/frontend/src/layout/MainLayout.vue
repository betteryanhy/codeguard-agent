<template>
  <el-container style="min-height: 100vh">
    <!-- Sidebar -->
    <el-aside :width="isCollapse ? '64px' : '240px'" class="sidebar">
      <div class="sidebar-header">
        <el-icon :size="28" color="#409eff" style="flex-shrink: 0"><Monitor /></el-icon>
        <span v-show="!isCollapse" class="sidebar-title">PR-CodeGuard</span>
      </div>

      <el-menu
        :default-active="route.path"
        :collapse="isCollapse"
        :collapse-transition="false"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#fff"
        @select="handleMenuSelect"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <template #title>仪表盘</template>
        </el-menu-item>
        <el-menu-item index="/risk">
          <el-icon><WarningFilled /></el-icon>
          <template #title>分支风险</template>
        </el-menu-item>
        <el-menu-item index="/tasks">
          <el-icon><List /></el-icon>
          <template #title>任务管理</template>
        </el-menu-item>
        <el-menu-item index="/strategy">
          <el-icon><Setting /></el-icon>
          <template #title>扫描策略</template>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Tools /></el-icon>
          <template #title>系统设置</template>
        </el-menu-item>
        <el-menu-item index="/audit-log">
          <el-icon><Document /></el-icon>
          <template #title>审计日志</template>
        </el-menu-item>
        <el-menu-item index="/assistant">
          <el-icon><ChatLineSquare /></el-icon>
          <template #title>问答助手</template>
        </el-menu-item>
      </el-menu>

      <!-- Collapse toggle -->
      <div class="sidebar-collapse" @click="isCollapse = !isCollapse">
        <el-icon><Fold v-if="!isCollapse" /><Expand v-else /></el-icon>
      </div>
    </el-aside>

    <!-- Right side -->
    <el-container>
      <!-- Header -->
      <el-header class="header">
        <div class="header-left">
          <span class="page-title">{{ route.meta?.title || 'PR-CodeGuard' }}</span>
        </div>
        <div class="header-right">
          <el-tag type="success" size="small" effect="plain" style="margin-right: 12px">运行中</el-tag>
          <el-dropdown trigger="click" @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="28" style="background: #409eff; vertical-align: middle">
                {{ userDisplayName }}
              </el-avatar>
              <span class="user-name" v-if="userDisplayName">{{ userDisplayName }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">个人信息</el-dropdown-item>
                <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
      </el-header>

      <!-- Main content -->
      <el-main class="main-content">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

const isCollapse = ref(false)

const userDisplayName = computed(() => {
  return authStore.user?.username || authStore.user?.name || 'Admin'
})

function handleMenuSelect(index) {
  router.push(index)
}

function handleCommand(command) {
  if (command === 'logout') {
    authStore.logout()
    router.push('/login')
  } else if (command === 'profile') {
    // Placeholder for profile
  }
}
</script>

<style scoped>
.sidebar {
  background: var(--bg-sidebar);
  display: flex;
  flex-direction: column;
  transition: width 0.3s;
  overflow: hidden;
}
.sidebar-header {
  height: 60px;
  display: flex;
  align-items: center;
  padding: 0 var(--sp-md);
  gap: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}
.sidebar-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-inverse);
  white-space: nowrap;
}
.sidebar :deep(.el-menu) {
  border-right: none;
  flex: 1;
}
.sidebar :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
  margin: 2px 8px;
  border-radius: var(--radius-md);
}
.sidebar :deep(.el-menu-item.is-active) {
  background: var(--color-primary) !important;
}
.sidebar :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.08);
}
.sidebar-collapse {
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffffa6;
  cursor: pointer;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
  transition: color 0.2s;
}
.sidebar-collapse:hover {
  color: #fff;
}
.header {
  height: 56px;
  background: var(--bg-header);
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  padding: 0 var(--sp-lg);
  justify-content: space-between;
  box-shadow: var(--shadow-header);
}
.header-left {
  display: flex;
  align-items: center;
}
.page-title {
  font-size: var(--fs-md);
  font-weight: 600;
  color: var(--text-primary);
}
.header-right {
  display: flex;
  align-items: center;
}
.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.2s;
}
.user-info:hover {
  background: #f5f7fa;
}
.user-name {
  font-size: var(--fs-base);
  color: var(--text-primary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main-content {
  background: var(--bg-page);
  padding: var(--sp-lg);
  overflow-y: auto;
  height: calc(100vh - 56px);
}
</style>
