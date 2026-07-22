<template>
  <div class="not-found">
    <div class="not-found-content">
      <div class="not-found-code">404</div>
      <h1 class="not-found-title">页面未找到</h1>
      <p class="not-found-desc">您访问的页面不存在或已被移除</p>
      <el-button type="primary" size="large" @click="goHome">
        <el-icon><HomeFilled /></el-icon>
        返回首页
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()

function goHome() {
  router.push('/')
}
</script>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - 120px);
}
.not-found-content {
  text-align: center;
  padding: 40px;
}
.not-found-code {
  font-size: 120px;
  font-weight: 800;
  line-height: 1;
  color: #e8eaed;
  letter-spacing: -4px;
  margin-bottom: -20px;
  position: relative;
}
.not-found-code::after {
  content: '404';
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  background: linear-gradient(135deg, #409eff 0%, #1890ff 50%, #52c41a 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  opacity: 0.5;
}
.not-found-title {
  font-size: 24px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px;
}
.not-found-desc {
  font-size: 14px;
  color: #909399;
  margin: 0 0 28px;
}
</style>
