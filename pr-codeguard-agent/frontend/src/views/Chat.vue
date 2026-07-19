<template>
  <div class="chat-container">
    <el-card shadow="never" class="chat-card">
      <template #header>
        <div style="display: flex; align-items: center; gap: 8px">
          <el-icon :size="20"><ChatDotRound /></el-icon>
          <span>Agent 智能对话</span>
          <el-tag v-if="connected" type="success" size="small" effect="plain">已连接</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">未配置 Key</el-tag>
        </div>
      </template>

      <!-- Messages area -->
      <div class="messages-area" ref="messagesRef">
        <div v-if="messages.length === 0" class="welcome">
          <el-icon :size="48" color="#409eff"><ChatLineSquare /></el-icon>
          <h3>你好！我是 CodeGuard Agent</h3>
          <p>你可以问我以下问题：</p>
          <div class="suggestions">
            <el-tag
              v-for="s in suggestions"
              :key="s"
              class="suggestion-tag"
              effect="plain"
              @click="sendMessage(s)"
            >
              {{ s }}
            </el-tag>
          </div>
        </div>

        <div
          v-for="(msg, i) in messages"
          :key="i"
          :class="['message', msg.role === 'user' ? 'message-user' : 'message-agent']"
        >
          <div class="message-bubble" :class="msg.role">
            <div class="message-content" v-html="renderContent(msg.content)"></div>
            <div v-if="msg.tool_calls && msg.tool_calls.length > 0" class="tool-info">
              <el-tag size="small" type="info" effect="plain">
                调用了 {{ msg.tool_calls.length }} 个工具
              </el-tag>
              <div v-for="tc in msg.tool_calls" :key="tc.tool" class="tool-call">
                <code>{{ tc.tool }}</code>
              </div>
            </div>
          </div>
        </div>

        <!-- Loading indicator -->
        <div v-if="loading" class="message message-agent">
          <div class="message-bubble agent loading-bubble">
            <span class="dot-pulse"></span>
          </div>
        </div>
      </div>

      <!-- Input area -->
      <div class="input-area">
        <el-input
          v-model="inputMessage"
          type="textarea"
          :rows="2"
          :disabled="loading || !connected"
          :placeholder="connected ? '输入你的问题，按 Enter 发送...' : '请先在 .env 中配置 AI_API_KEY'"
          @keydown.enter.exact="handleSend"
          resize="none"
          class="chat-input"
        >
          <template #prefix>
            <el-icon><EditPen /></el-icon>
          </template>
        </el-input>
        <div class="input-actions">
          <el-button
            type="primary"
            :loading="loading"
            :disabled="!inputMessage.trim() || !connected"
            @click="handleSend"
          >
            {{ loading ? '思考中...' : '发送' }}
          </el-button>
          <el-button
            v-if="messages.length > 0"
            type="danger"
            text
            size="small"
            @click="clearChat"
          >
            清空对话
          </el-button>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

const messagesRef = ref(null)
const inputMessage = ref('')
const messages = ref([])
const loading = ref(false)
const connected = ref(false)

const suggestions = [
  '显示今天的日报',
  '查看最近的扫描趋势',
  '搜索知识库中的 Terraform 变更',
  '当前扫描策略是什么？',
  '告警系统状态如何？',
]

onMounted(async () => {
  // Check if AI is configured
  try {
    const res = await api.healthCheck()
    connected.value = true  // Agent is running
  } catch {
    connected.value = false
  }
})

async function handleSend() {
  const text = inputMessage.value.trim()
  if (!text || loading.value) return

  // Add user message
  messages.value.push({
    role: 'user',
    content: text,
  })
  inputMessage.value = ''
  loading.value = true

  scrollToBottom()

  try {
    const history = messages.value
      .filter(m => m.role !== 'system')
      .slice(-10, -1)  // Exclude current user message, keep last 10
      .map(m => ({ role: m.role, content: m.content }))

    const res = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        history: history,
      }),
    })

    if (!res.ok) throw new Error(`HTTP ${res.status}`)

    const data = await res.json()

    // Add agent response
    messages.value.push({
      role: 'assistant',
      content: data.reply || '（没有收到回复）',
      tool_calls: data.tool_calls || [],
    })
  } catch (e) {
    messages.value.push({
      role: 'assistant',
      content: '❌ 请求失败：' + (e.message || '网络错误'),
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function sendMessage(text) {
  inputMessage.value = text
  handleSend()
}

function clearChat() {
  messages.value = []
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function renderContent(text) {
  if (!text) return ''
  // Basic markdown-like rendering
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^### (.+)$/gm, '<h4>$1</h4>')
    .replace(/^## (.+)$/gm, '<h3>$1</h3>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
}
</script>

<style scoped>
.chat-container {
  max-width: 900px;
  margin: 0 auto;
  height: calc(100vh - 140px);
  display: flex;
  flex-direction: column;
}

.chat-card {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.chat-card :deep(.el-card__body) {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0;
  overflow: hidden;
}

.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  background: #f8f9fb;
}

.welcome {
  text-align: center;
  padding: 60px 20px;
  color: #606266;
}

.welcome h3 {
  margin: 16px 0 8px;
  font-size: 20px;
  color: #303133;
}

.welcome p {
  margin: 0 0 20px;
  font-size: 14px;
  color: #909399;
}

.suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 500px;
  margin: 0 auto;
}

.suggestion-tag {
  cursor: pointer;
  font-size: 13px;
  padding: 4px 12px;
  border-radius: 16px;
  transition: all 0.2s;
}

.suggestion-tag:hover {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
}

.message {
  margin-bottom: 16px;
  display: flex;
}

.message-user {
  justify-content: flex-end;
}

.message-agent {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
  word-break: break-word;
}

.message-bubble.user {
  background: #409eff;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message-bubble.agent {
  background: #fff;
  color: #303133;
  border: 1px solid #e4e7ed;
  border-bottom-left-radius: 4px;
}

.message-content {
  white-space: pre-wrap;
}

.message-content :deep(code) {
  background: #f0f2f5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: 'SFMono-Regular', Consolas, monospace;
}

.message-content :deep(li) {
  margin-left: 16px;
  margin-bottom: 4px;
}

.tool-info {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #eee;
}

.tool-call code {
  font-size: 12px;
  background: #f0f2f5;
  padding: 2px 6px;
  border-radius: 4px;
  color: #909399;
}

.loading-bubble {
  padding: 16px 24px !important;
}

.dot-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #409eff;
  animation: pulse 1.2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.input-area {
  padding: 16px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}

.chat-input {
  margin-bottom: 8px;
}

.chat-input :deep(.el-textarea__inner) {
  border-radius: 8px;
  font-size: 14px;
}

.input-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
