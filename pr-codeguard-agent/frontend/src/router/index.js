import { createRouter, createWebHashHistory } from 'vue-router'
import MainLayout from '../layout/MainLayout.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/',
    component: MainLayout,
    redirect: '/dashboard',
    children: [
      { path: '/dashboard', name: 'Dashboard', component: () => import('../views/Dashboard.vue'), meta: { title: '仪表盘' } },
      { path: '/risk', name: 'Risk', component: () => import('../views/Risk.vue'), meta: { title: '分支风险' } },
      { path: '/tasks', name: 'Tasks', component: () => import('../views/Tasks.vue'), meta: { title: '任务管理' } },
      { path: '/strategy', name: 'Strategy', component: () => import('../views/Strategy.vue'), meta: { title: '扫描策略' } },
      { path: '/settings', name: 'Settings', component: () => import('../views/Settings.vue'), meta: { title: '系统设置' } },
      { path: '/audit-log', name: 'AuditLog', component: () => import('../views/AuditLog.vue'), meta: { title: '审计日志' } },
      { path: '/assistant', name: 'Assistant', component: () => import('../views/Assistant.vue'), meta: { title: '问答助手' } },
      { path: '/:pathMatch(.*)*', name: 'NotFound', component: () => import('../views/NotFound.vue'), meta: { title: '页面未找到' } },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

// 导航守卫
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/dashboard')
  } else {
    next()
  }
})

export default router
