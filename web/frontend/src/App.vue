<script setup lang="ts">
import { computed } from 'vue'
import { NConfigProvider, darkTheme, NMessageProvider, NDialogProvider } from 'naive-ui'
import { useSettingsStore } from '@/stores/settings'
import { useSync } from '@/composables/useSync'
import { naiveThemeOverrides } from '@/utils/naiveTheme'

const settings = useSettingsStore()

// 服务端双写同步：全局唯一的 watcher 实例（登录后会话/收藏防抖提交服务端）
useSync()

// settings 里的 theme 一变，Naive UI 的明暗主题自动跟随（响应式）
const isDark = computed(() => settings.theme === 'dark')
</script>

<template>
  <n-config-provider
    :theme="isDark ? darkTheme : null"
    :theme-overrides="naiveThemeOverrides"
  >
    <!-- message/dialog provider：组件里 useMessage()/useDialog() 的前提 -->
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>
