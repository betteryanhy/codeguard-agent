import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '',
  timeout: 30000,
})

// === System ===
export const healthCheck = () => api.get('/health')

// === Discovery ===
export const listProjects = () => api.get('/api/v1/discovery/projects')
export const scanDiscovery = () => api.post('/api/v1/discovery/scan')
export const registerWebhooks = () => api.post('/api/v1/discovery/register-webhooks')
export const registerProjectWebhook = (id) => api.post(`/api/v1/discovery/projects/${id}/register`)
export const webhookHealth = () => api.get('/api/v1/discovery/webhook-health')
export const checkWebhookHealth = () => api.post('/api/v1/discovery/webhook-health/check')

// === Tasks / Results ===
export const listTasks = (skip = 0, limit = 20) => api.get('/api/v1/tasks/', { params: { skip, limit } })
export const getResult = (taskId) => api.get(`/api/v1/results/${taskId}`)
export const getResultSummary = (taskId) => api.get(`/api/v1/results/${taskId}/summary`)

// === Strategy ===
export const getDefaultStrategy = () => api.get('/api/v1/strategy/default')
export const updateDefaultStrategy = (data) => api.put('/api/v1/strategy/default', data)
export const listStrategies = () => api.get('/api/v1/strategy/repos')
export const getRepoStrategy = (repoUrl) => api.get(`/api/v1/strategy/repos/${encodeURIComponent(repoUrl)}`)
export const setRepoStrategy = (repoUrl, data) => api.put(`/api/v1/strategy/repos/${encodeURIComponent(repoUrl)}`, data)
export const deleteRepoStrategy = (repoUrl) => api.delete(`/api/v1/strategy/repos/${encodeURIComponent(repoUrl)}`)

// === Knowledge ===
export const searchKnowledge = (q, scope = 'all', nResults = 5, repoUrl = '') =>
  api.get('/api/v1/knowledge/search', { params: { q, scope, n_results: nResults, repo_url: repoUrl } })
export const listKnowledgeMrs = (repoUrl = '', limit = 20) =>
  api.get('/api/v1/knowledge/mrs', { params: { repo_url: repoUrl, limit } })

// === Reports ===
export const getDailyReport = (dateStr = '', repoUrl = '') =>
  api.get('/api/v1/reports/daily', { params: { date_str: dateStr, repo_url: repoUrl } })
export const getTrends = (period = 'weekly', count = 8, repoUrl = '') =>
  api.get('/api/v1/reports/trends', { params: { period, count, repo_url: repoUrl } })

// === Alerts ===
export const getAlertStatus = () => api.get('/api/v1/alerts/status')
export const testAlert = (title, message) => api.post('/api/v1/alerts/test', { title, message })
export const sendReport = (dateStr = '') => api.post('/api/v1/alerts/send-report', null, { params: { date_str: dateStr } })

// === Config ===
export const listRepositories = () => api.get('/api/v1/config/repositories')
export const registerRepository = (data) => api.post('/api/v1/config/repositories', data)
export const getRepository = (repoId) => api.get(`/api/v1/config/repositories/${repoId}`)
export const disableRepository = (repoId) => api.post(`/api/v1/config/repositories/${repoId}/disable`)
export const enableRepository = (repoId) => api.post(`/api/v1/config/repositories/${repoId}/enable`)

export default api
