<script setup lang="ts">
import { computed, h, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NDropdown, NAvatar, NIcon, useDialog } from 'naive-ui'
import {
  MoonOutline,
  SunnyOutline,
  LogOutOutline,
  PersonOutline,
  StarOutline,
  TrashOutline,
  SettingsOutline,
  ChevronDownOutline,
} from '@vicons/ionicons5'
import ProfileModal from '@/components/common/ProfileModal.vue'
import FavoritesModal from '@/components/common/FavoritesModal.vue'
import SettingsModal from '@/components/common/SettingsModal.vue'
import { useSettingsStore } from '@/stores/settings'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'

const settings = useSettingsStore()
const auth = useAuthStore()
const sessions = useSessionsStore()
const dialog = useDialog()
const router = useRouter()

const isDark = computed(() => settings.theme === 'dark')

// 弹窗开关
const showProfile = ref(false)
const showFavorites = ref(false)
const showSettings = ref(false)

/** 头像颜色：个人资料设置的颜色，未设置用品牌蓝 */
const avatarColor = computed(() => auth.profile?.avatarColor || 'var(--color-brand-500)')

/** 下拉菜单头部：头像 + 昵称 + 账号（旧版 user-dropdown-head 语义） */
function renderHead() {
  return h('div', { class: 'flex items-center gap-2.5 px-2 py-1.5' }, [
    h(
      'div',
      {
        class: 'flex h-9 w-9 shrink-0 items-center justify-center overflow-hidden rounded-full text-[13px] font-semibold text-white',
        style: { backgroundColor: auth.profile?.avatarColor || '#1a5fb4' },
      },
      auth.profile?.avatarData
        ? h('img', { src: auth.profile.avatarData, class: 'h-full w-full object-cover' })
        : (auth.displayLabel || 'U').slice(0, 2),
    ),
    h('div', { class: 'min-w-0' }, [
      h('div', { class: 'truncate text-[13px] font-semibold text-ink' }, auth.displayLabel || '用户'),
      h('div', { class: 'text-[11px] text-muted' }, `@${auth.username || ''}`),
    ]),
  ])
}

/** 菜单项图标统一 16px + 灰调，与整体风格一致（直接 h(图标) 会用到默认大尺寸） */
function menuIcon(icon: typeof PersonOutline) {
  return () => h(NIcon, { size: 16, class: 'text-muted' }, { default: () => h(icon) })
}

const userOptions = computed(() => [
  { type: 'render' as const, key: 'head', render: renderHead },
  { type: 'divider' as const, key: 'd1' },
  { label: '设置', key: 'settings', icon: menuIcon(SettingsOutline) },
  { label: '个人资料', key: 'profile', icon: menuIcon(PersonOutline) },
  { label: '我的收藏', key: 'favorites', icon: menuIcon(StarOutline) },
  { label: '清空对话记录', key: 'clear-sessions', icon: menuIcon(TrashOutline) },
  { type: 'divider' as const, key: 'd2' },
  { label: '退出登录', key: 'logout', icon: menuIcon(LogOutOutline) },
])

function onUserSelect(key: string) {
  if (key === 'settings') {
    showSettings.value = true
  } else if (key === 'profile') {
    showProfile.value = true
  } else if (key === 'favorites') {
    showFavorites.value = true
  } else if (key === 'clear-sessions') {
    dialog.warning({
      title: '清空对话记录',
      content: '确定清空所有对话记录？此操作不可恢复。',
      positiveText: '清空',
      negativeText: '取消',
      onPositiveClick: () => sessions.clearAllSessions(),
    })
  } else if (key === 'logout') {
    // 清理会话数据（按用户隔离的持久化 key 会在下次登录重新加载）
    sessions.$reset()
    auth.logout()
    router.push('/login')
  }
}
</script>

<template>
  <header
    class="flex h-14 shrink-0 items-center justify-between border-b border-line bg-brand-600 px-4 text-white"
  >
    <div class="flex items-center gap-2.5">
      <span class="text-xl leading-none">⚖️</span>
      <span class="text-base font-semibold tracking-wide">法信通 LawTrust</span>
    </div>

    <div class="flex items-center gap-2">
      <!-- 主题切换：一个开关同时驱动 Tailwind 令牌与 Naive UI 主题 -->
      <n-button
        quaternary
        circle
        :focusable="false"
        title="切换亮暗主题"
        @click="settings.toggleTheme()"
      >
        <template #icon>
          <n-icon :component="isDark ? SunnyOutline : MoonOutline" />
        </template>
      </n-button>

      <!-- 用户菜单：个人资料 / 我的收藏 / 清空对话记录 / 退出登录 -->
      <n-dropdown trigger="click" :options="userOptions" @select="onUserSelect">
        <button
          class="flex items-center gap-1.5 rounded-full py-1 pl-1 pr-2 transition-colors hover:bg-white/10"
          title="个人中心"
        >
          <n-avatar
            round
            :size="26"
            :src="auth.profile?.avatarData || undefined"
            :style="{ backgroundColor: avatarColor }"
          >
            {{ (auth.displayLabel || 'U').slice(0, 2) }}
          </n-avatar>
          <span class="hidden text-[13px] text-white/90 sm:inline">
            {{ auth.displayLabel || '用户' }}
          </span>
          <n-icon :component="ChevronDownOutline" size="14" class="text-white/60" />
        </button>
      </n-dropdown>
    </div>

    <!-- 设置 / 个人资料 / 我的收藏 弹窗 -->
    <SettingsModal :show="showSettings" @close="showSettings = false" />
    <ProfileModal :show="showProfile" @close="showProfile = false" />
    <FavoritesModal :show="showFavorites" @close="showFavorites = false" />
  </header>
</template>
