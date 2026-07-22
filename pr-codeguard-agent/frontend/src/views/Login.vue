<template>
  <div class="login-wrapper">
    <div class="login-bg-pattern"></div>
    <div class="login-card">
      <div class="login-header">
        <div class="login-logo">
          <el-icon :size="36" color="#fff"><Monitor /></el-icon>
        </div>
        <h1>PR-CodeGuard</h1>
        <p>企业级代码安全扫描平台</p>
      </div>
      <el-form @submit.prevent="handleLogin" :model="form">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" prefix-icon="User" size="large" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            prefix-icon="Lock"
            show-password
            size="large"
            @keyup.enter="handleLogin"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" size="large" style="width: 100%" @click="handleLogin">
            {{ loading ? '登录中…' : '登 录' }}
          </el-button>
        </el-form-item>
        <div v-if="error" class="login-error">{{ error }}</div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({
  username: '',
  password: '',
})
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  if (!form.username || !form.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await authStore.login(form.username, form.password)
    router.push('/dashboard')
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f1a2e 0%, #1a3050 40%, #2d4a6e 70%, #1a3050 100%);
  position: relative;
  overflow: hidden;
}
.login-bg-pattern {
  position: absolute;
  inset: 0;
  background-image:
    radial-gradient(ellipse at 20% 50%, rgba(64,158,255,0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 20%, rgba(82,196,26,0.06) 0%, transparent 50%),
    radial-gradient(ellipse at 50% 80%, rgba(250,140,22,0.05) 0%, transparent 50%);
  pointer-events: none;
}
.login-card {
  width: 400px;
  padding: 40px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.2);
  position: relative;
  animation: card-enter 0.4s ease-out;
}
@keyframes card-enter {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.login-header {
  text-align: center;
  margin-bottom: 32px;
}
.login-logo {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: linear-gradient(135deg, #1890ff, #096dd9);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  box-shadow: 0 4px 12px rgba(24,144,255,0.35);
}
.login-header h1 {
  margin: 0 0 4px;
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}
.login-header p {
  margin: 0;
  font-size: 14px;
  color: #909399;
}
.login-error {
  text-align: center;
  color: #f56c6c;
  font-size: 13px;
  margin-top: 8px;
}
</style>
