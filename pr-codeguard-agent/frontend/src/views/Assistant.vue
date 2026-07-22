<template>
  <div style="padding: 20px">
    <!-- ══════════════════════════════════════════════════
         统一智能助手（对话 + 知识搜索）
         ══════════════════════════════════════════════════ -->

    <!-- ── 对话模式 ── -->
    <div v-show="mode === 'chat'" class="chat-container">
      <el-card shadow="never" class="chat-card">
        <template #header>
          <div style="display: flex; align-items: center; gap: 8px">
            <el-icon :size="20"><ChatDotRound /></el-icon>
            <span>Agent 智能对话</span>
            <el-tag v-if="connected" type="success" size="small" effect="plain">已连接</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">未配置 Key</el-tag>
            <div style="margin-left: auto">
              <el-button size="small" text @click="mode = 'search'">
                <el-icon><Search /></el-icon> 切换到知识搜索
              </el-button>
            </div>
          </div>
        </template>

        <!-- Messages -->
        <div class="messages-area" ref="messagesRef">
          <div v-if="messages.length === 0" class="welcome">
            <el-icon :size="48" color="#409eff"><ChatLineSquare /></el-icon>
            <h3>你好！我是 CodeGuard Agent</h3>
            <p>你可以问我以下问题，或在顶部切换到「知识搜索」进行精确检索：</p>
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

          <div v-if="chatLoading && !streamingContent" class="message message-agent">
            <div class="message-bubble agent loading-bubble">
              <span class="dot-pulse"></span>
            </div>
          </div>
        </div>

        <!-- Input -->
        <div class="input-area">
          <el-input
            v-model="inputMessage"
            type="textarea"
            :rows="2"
            :disabled="chatLoading || !connected"
            :placeholder="connected ? '输入你的问题，按 Enter 发送...' : '请先在 .env 中配置 AI_API_KEY'"
            @keydown.enter.exact="handleSend"
            resize="none"
            class="chat-input"
          />
          <div class="input-actions">
            <el-button
              type="primary"
              :loading="chatLoading"
              :disabled="!inputMessage.trim() || !connected"
              @click="handleSend"
            >
              {{ chatLoading ? '思考中...' : '发送' }}
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

    <!-- ── 知识搜索模式 ── -->
    <div v-show="mode === 'search'">
      <el-card shadow="never" style="margin-bottom: 20px">
        <template #header>
          <div style="display: flex; align-items: center; gap: 8px">
            <el-icon :size="20"><Search /></el-icon>
            <span>知识库搜索</span>
            <div style="margin-left: auto">
              <el-button size="small" text @click="mode = 'chat'">
                <el-icon><ChatDotRound /></el-icon> 切换到对话
              </el-button>
            </div>
          </div>
        </template>
        <el-form :inline="true" :model="searchForm">
          <el-form-item label="关键词" style="margin-bottom: 0">
            <el-input
              v-model="searchForm.q"
              placeholder="输入搜索关键词"
              clearable
              style="width: 300px"
              @keyup.enter="handleSearch"
            />
          </el-form-item>
          <el-form-item label="搜索范围" style="margin-bottom: 0">
            <el-select v-model="searchForm.scope" style="width: 140px">
              <el-option label="全部" value="all" />
              <el-option label="代码" value="code" />
              <el-option label="MR" value="mr" />
            </el-select>
          </el-form-item>
          <el-form-item style="margin-bottom: 0">
            <el-button type="primary" @click="handleSearch" :loading="searchLoading">搜索</el-button>
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

      <!-- Recent MR records -->
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
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import * as api from '../api'

// ═══════════════════════════════════════════════════════════════════
//  模式切换
// ═══════════════════════════════════════════════════════════════════
const mode = ref('chat')       // 'chat' | 'search'

// ═══════════════════════════════════════════════════════════════════
//  对话模块
// ═══════════════════════════════════════════════════════════════════
const STORAGE_KEY = 'codeguard_chat_messages'
const messagesRef = ref(null)
const inputMessage = ref('')
const messages = ref([])
const chatLoading = ref(false)
const connected = ref(false)
const streamingContent = ref('')
const abortController = ref(null)

const suggestions = [
  '显示今天的日报',
  '查看最近的扫描趋势',
  '搜索知识库中的 Terraform 变更',
  '当前扫描策略是什么？',
  '告警系统状态如何？',
]

// Load messages from localStorage on mount
function loadMessages() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (Array.isArray(parsed) && parsed.length > 0) {
        messages.value = parsed
      }
    }
  } catch {
    // ignore
  }
}

// Save messages to localStorage
function saveMessages() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(messages.value))
  } catch {
    // ignore
  }
}

// Watch messages and save on change
watch(messages, saveMessages, { deep: true })

onMounted(async () => {
  loadMessages()
  try {
    await api.healthCheck()
    connected.value = true
  } catch {
    connected.value = false
  }
})

async function handleSend() {
  const text = inputMessage.value.trim()
  if (!text || chatLoading.value) return

  messages.value.push({ role: 'user', content: text })
  inputMessage.value = ''
  chatLoading.value = true
  streamingContent.value = ''
  scrollToBottom()

  const history = messages.value
    .filter(m => m.role !== 'system')
    .slice(-10, -1)
    .map(m => ({ role: m.role, content: m.content }))

  // Use SSE streaming
  try {
    const controller = new AbortController()
    abortController.value = controller

    const response = await fetch('/api/v1/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history }),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let toolCalls = []

    // Add a placeholder assistant message for streaming
    messages.value.push({
      role: 'assistant',
      content: '',
      tool_calls: [],
      streaming: true,
    })

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6).trim()
        if (!data) continue

        try {
          const event = JSON.parse(data)

          if (event.type === 'start') {
            toolCalls = event.tool_calls || []
            // Update the last message with tool calls
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg) {
              lastMsg.tool_calls = toolCalls
            }
          } else if (event.type === 'token') {
            // Append token to the last message
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg) {
              lastMsg.content += event.content
            }
            streamingContent.value += event.content
            scrollToBottom()
          } else if (event.type === 'end') {
            // Mark streaming as complete
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg) {
              delete lastMsg.streaming
            }
          } else if (event.type === 'error') {
            const lastMsg = messages.value[messages.value.length - 1]
            if (lastMsg) {
              lastMsg.content = '❌ ' + event.content
              delete lastMsg.streaming
            }
          }
        } catch {
          // skip malformed JSON
        }
      }
    }

    // Ensure streaming flag is removed
    const lastMsg = messages.value[messages.value.length - 1]
    if (lastMsg) {
      delete lastMsg.streaming
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      // User cancelled, keep partial content
      const lastMsg = messages.value[messages.value.length - 1]
      if (lastMsg) delete lastMsg.streaming
    } else {
      messages.value.push({
        role: 'assistant',
        content: '❌ 请求失败：' + (e.message || '网络错误'),
        tool_calls: [],
      })
    }
  } finally {
    chatLoading.value = false
    streamingContent.value = ''
    abortController.value = null
    scrollToBottom()
  }
}

function sendMessage(text) {
  inputMessage.value = text
  handleSend()
}

function clearChat() {
  messages.value = []
  localStorage.removeItem(STORAGE_KEY)
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

// ═══════════════════════════════════════════════════════════════════
//  知识搜索模块
// ═══════════════════════════════════════════════════════════════════
const searchForm = reactive({
  q: '',
  scope: 'all',
})
const searchResults = ref([])
const searched = ref(false)
const searchLoading = ref(false)

const handleSearch = async () => {
  if (!searchForm.q.trim()) {
    ElMessage.warning('请输入搜索关键词')
    return
  }
  searched.value = true
  searchLoading.value = true
  try {
    const res = await api.searchKnowledge(searchForm.q.trim(), searchForm.scope)
    searchResults.value = res.data?.results || res.data || []
  } catch (e) {
    ElMessage.error('搜索失败: ' + (e.response?.data?.detail || e.message))
    searchResults.value = []
  } finally {
    searchLoading.value = false
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

<style scoped>
/* ─── Chat styles ─── */
.chat-container {
  max-width: 900px;
  margin: 0 auto;
  height: calc(100vh - 200px);
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
.message-user { justify-content: flex-end; }
.message-agent { justify-content: flex-start; }
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
.message-content { white-space: pre-wrap; }
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
.tool-info { margin-top: 8px; padding-top: 8px; border-top: 1px solid #eee; }
.tool-call code { font-size: 12px; background: #f0f2f5; padding: 2px 6px; border-radius: 4px; color: #909399; }
.loading-bubble { padding: 16px 24px !important; }
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
.input-area { padding: 16px; border-top: 1px solid #e4e7ed; background: #fff; }
.chat-input { margin-bottom: 8px; }
.chat-input :deep(.el-textarea__inner) { border-radius: 8px; font-size: 14px; }
.input-actions { display: flex; justify-content: space-between; align-items: center; }
</style>
