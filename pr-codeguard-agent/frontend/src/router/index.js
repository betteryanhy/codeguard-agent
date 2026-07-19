import { createRouter, createWebHashHistory } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'

const routes = [
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      {
        path: '/dashboard',
        name: 'Dashboard',
        component: () => import('../views/Dashboard.vue'),
        meta: { title: '概览' },
      },
      {
        path: '/repositories',
        name: 'Repositories',
        component: () => import('../views/Repositories.vue'),
        meta: { title: '仓库列表' },
      },
      {
        path: '/tasks',
        name: 'Tasks',
        component: () => import('../views/Tasks.vue'),
        meta: { title: '扫描任务' },
      },
      {
        path: '/tasks/:id',
        name: 'TaskDetail',
        component: () => import('../views/TaskDetail.vue'),
        meta: { title: '任务详情' },
      },
      {
        path: '/strategy',
        name: 'Strategy',
        component: () => import('../views/Strategy.vue'),
        meta: { title: '扫描策略' },
      },
      {
        path: '/knowledge',
        name: 'Knowledge',
        component: () => import('../views/Knowledge.vue'),
        meta: { title: '知识库搜索' },
      },
      {
        path: '/reports',
        name: 'Reports',
        component: () => import('../views/Reports.vue'),
        meta: { title: '日报 & 趋势' },
      },
      {
        path: '/alerts',
        name: 'Alerts',
        component: () => import('../views/Alerts.vue'),
        meta: { title: '告警系统' },
      },
      {
        path: '/chat',
        name: 'Chat',
        component: () => import('../views/Chat.vue'),
        meta: { title: 'Agent 对话' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
