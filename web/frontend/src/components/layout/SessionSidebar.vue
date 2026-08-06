<script setup lang="ts">
import { ref } from 'vue'
import { NIcon, NPopconfirm, useDialog } from 'naive-ui'
import { AddOutline, ChatbubbleOutline, TrashOutline, CreateOutline } from '@vicons/ionicons5'
import RenameModal from '@/components/common/RenameModal.vue'
import { useSessionsStore } from '@/stores/sessions'

const sessions = useSessionsStore()
const dialog = useDialog()

// 重命名弹窗状态
const renameShow = ref(false)
const renamingId = ref('')

function openRename(id: string) {
  renamingId.value = id
  renameShow.value = true
}
function saveRename(title: string) {
  sessions.renameSession(renamingId.value, title)
  renameShow.value = false
}

function clearAll() {
  dialog.warning({
    title: '清空所有会话',
    content: '确定清空所有对话记录？此操作不可恢复。',
    positiveText: '清空',
    negativeText: '取消',
    onPositiveClick: () => sessions.clearAllSessions(),
  })
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  if (sameDay) return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
  const yesterday = new Date(now.getTime() - 86400000)
  if (d.toDateString() === yesterday.toDateString()) return '昨天'
  return `${d.getMonth() + 1}月${d.getDate()}日`
}
</script>

<template>
  <aside
    class="flex w-[260px] shrink-0 flex-col border-r border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800"
  >
    <!-- 新建会话（深色主按钮） -->
    <div class="p-3">
      <button
        class="flex w-full items-center justify-center gap-1.5 rounded-lg border border-slate-200 bg-white py-2.5 text-[15px] font-medium text-slate-700 shadow-sm transition-colors hover:bg-slate-100"
        @click="sessions.createSession(true)"
      >
        <n-icon :component="AddOutline" class="text-base" />
        新建会话
      </button>
    </div>

    <!-- 会话列表 -->
    <div class="flex-1 space-y-0.5 overflow-y-auto px-2 pb-2">
      <button
        v-for="s in sessions.sessions"
        :key="s.id"
        class="group flex w-full items-center gap-2 border-l-4 px-2.5 py-2 text-left text-[13px] transition-colors"
        :class="
          s.id === sessions.currentSessionId
            ? 'border-blue-600 bg-white text-blue-700 shadow-sm dark:bg-slate-700 dark:text-blue-300'
            : 'border-transparent text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700/50'
        "
        @click="sessions.switchSession(s.id)"
      >
        <n-icon :component="ChatbubbleOutline" class="shrink-0" />
        <span class="flex-1 truncate">{{ s.title }}</span>
        <span class="shrink-0 text-[10px] text-slate-400 group-hover:hidden">
          {{ formatTime(s.updatedAt) }}
        </span>
        <span class="hidden shrink-0 items-center gap-1 group-hover:flex">
          <n-icon
            :component="CreateOutline"
            class="cursor-pointer text-slate-400 hover:text-blue-600"
            title="重命名"
            @click.stop="openRename(s.id)"
          />
          <n-popconfirm
            positive-text="删除"
            negative-text="取消"
            @positive-click="sessions.deleteSession(s.id)"
          >
            <template #trigger>
              <n-icon
                :component="TrashOutline"
                class="cursor-pointer text-slate-400 hover:text-blue-600"
                title="删除"
                @click.stop
              />
            </template>
            <span class="text-[13px]">确定删除该会话？</span>
          </n-popconfirm>
        </span>
      </button>
    </div>

    <!-- 底部：清空入口 -->
    <div class="border-t border-slate-200 p-3 dark:border-slate-700">
      <button
        class="w-full rounded-lg px-2.5 py-1.5 text-left text-[11px] text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-600"
        @click="clearAll"
      >
        清空所有会话
      </button>
    </div>

    <!-- 重命名弹窗 -->
    <RenameModal
      :show="renameShow"
      :initial="sessions.sessions.find((s) => s.id === renamingId)?.title || ''"
      @confirm="saveRename"
      @cancel="renameShow = false"
    />
  </aside>
</template>
