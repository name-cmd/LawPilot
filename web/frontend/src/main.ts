import { createApp } from 'vue'
import { createPinia } from 'pinia'
import piniaPluginPersistedstate from 'pinia-plugin-persistedstate'
import naive from 'naive-ui'
import App from './App.vue'
import router from './router'
import { useSettingsStore } from '@/stores/settings'
import './assets/styles/main.css'
import './assets/styles/base.css'

const app = createApp(App)

const pinia = createPinia()
pinia.use(piniaPluginPersistedstate) // store 持久化插件：persist: true 的 store 自动写 localStorage
app.use(pinia)

// 应用启动时把已持久化的主题应用到 html 根元素（与 index.html 防闪烁脚本保持一致）
useSettingsStore(pinia).applyTheme()

app.use(router)
app.use(naive) // 完整引入 Naive UI（初学者友好，后续如需优化体积再改按需导入）
app.mount('#app')
