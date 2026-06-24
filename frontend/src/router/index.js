import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: () => import('./views/Dashboard.vue') },
  { path: '/flow', name: 'flow', component: () => import('./views/FlowAnalysis.vue') },
  { path: '/prediction', name: 'prediction', component: () => import('./views/Prediction.vue') },
  { path: '/optimization', name: 'optimization', component: () => import('./views/Optimization.vue') },
  { path: '/carbon', name: 'carbon', component: () => import('./views/CarbonAnalysis.vue') },
  { path: '/simulation', name: 'simulation', component: () => import('./views/Simulation.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
