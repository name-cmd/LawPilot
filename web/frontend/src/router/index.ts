import { createRouter, createWebHashHistory } from 'vue-router'
import LoginView from '@/views/LoginView.vue'
import ChatView from '@/views/ChatView.vue'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useFavoritesStore } from '@/stores/favorites'

/**
 * 路由表。
 * 采用 hash 模式（URL 形如 /ui/#/chat）：
 * 生产环境前端挂在 /ui 路径下由 FastAPI 静态服务，
 * hash 模式刷新任意页面都不会触发后端 404，无需后端配合。
 */
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView },
    { path: '/', name: 'chat', component: ChatView },
    // M4 新增：{ path: '/report', name: 'report', component: ReportView },
  ],
})

// 模块级标志：restoreSession 只做一次（刷新页面不重复 verify）
let restored = false

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const sessions = useSessionsStore()
  const favorites = useFavoritesStore()

  if (!restored) {
    restored = true
    const ok = await auth.restoreSession()
    if (ok) {
      await sessions.loadForCurrentUser()
      favorites.loadForCurrentUser()
    } else {
      await auth.logout()
    }
  }

  const loggedIn = auth.isLoggedIn
  if (to.name !== 'login' && !loggedIn) return { name: 'login' }
  if (to.name === 'login' && loggedIn) return { name: 'chat' }
  return true
})

export default router
