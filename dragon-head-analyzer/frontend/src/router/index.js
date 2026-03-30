import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Dashboard',
    component: () => import('../views/Dashboard.vue'),
  },
  {
    path: '/zt-pool',
    name: 'ZtPool',
    component: () => import('../views/ZtPool.vue'),
  },
  {
    path: '/stock/:code',
    name: 'StockDetail',
    component: () => import('../views/StockDetail.vue'),
  },
  {
    path: '/boards',
    name: 'Boards',
    component: () => import('../views/Boards.vue'),
  },
  {
    path: '/logs',
    name: 'Logs',
    component: () => import('../views/Logs.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
