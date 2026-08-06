<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { NModal, NInput, NEmpty, useMessage } from 'naive-ui'
import { useFavoritesStore } from '@/stores/favorites'
import type { Favorite } from '@/stores/favorites'

/**
 * 我的收藏弹窗（原样迁移旧版功能）：收藏列表 + 编辑标题/备注 + 删除。
 * 收藏数据按用户名隔离持久化（lawtrust_favorites_v2_{username}）。
 */

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const favorites = useFavoritesStore()
const toast = useMessage()

// 编辑弹窗状态
const editing = ref<Favorite | null>(null)
const editForm = reactive({ title: '', note: '' })

function openEdit(f: Favorite) {
  editing.value = f
  editForm.title = f.title
  editForm.note = f.note
}

function saveEdit() {
  if (editing.value) {
    favorites.updateFavorite(editing.value.id, editForm.title, editForm.note)
    toast.success('收藏已更新')
  }
  editing.value = null
}

function remove(f: Favorite) {
  favorites.removeFavorite(f.id)
  toast.info('已删除收藏')
}

function fmtTime(ts: number) {
  return new Date(ts).toLocaleString('zh-CN', { hour12: false })
}

watch(
  () => props.show,
  (open) => {
    if (open) favorites.loadForCurrentUser()
  },
)
</script>

<template>
  <n-modal
    :show="props.show"
    preset="card"
    title="我的收藏"
    style="width: 520px; max-height: 80vh"
    :content-style="{ overflowY: 'auto', maxHeight: '60vh' }"
    @update:show="(v: boolean) => !v && emit('close')"
  >
    <n-empty
      v-if="!favorites.favorites.length"
      description="暂无收藏，在对话中点击 ☆ 收藏"
      class="py-10"
    />

    <div v-else class="space-y-2">
      <div
        v-for="f in favorites.favorites" :key="f.id"
        class="rounded-xl border border-line bg-surface p-3"
      >
        <div class="flex items-center justify-between gap-2">
          <span class="truncate text-[13px] font-medium text-ink">{{ f.title }}</span>
          <span v-if="f.meta?.trust?.overall_score != null" class="shrink-0 text-[12px] font-semibold text-brand-500">
            {{ f.meta.trust.overall_score }}分
          </span>
        </div>
        <div class="mt-0.5 text-[11px] text-muted">
          {{ fmtTime(f.createdAt) }}<span v-if="f.note"> · {{ f.note }}</span>
        </div>
        <p class="mt-1 text-[11px] leading-relaxed text-muted">
          {{ f.content.slice(0, 120) }}{{ f.content.length > 120 ? '…' : '' }}
        </p>
        <div class="mt-1.5 flex gap-3 text-[11px]">
          <button class="text-brand-500 hover:underline" @click="openEdit(f)">编辑</button>
          <button class="text-danger hover:underline" @click="remove(f)">删除</button>
        </div>
      </div>
    </div>

    <div class="mt-3 flex justify-end">
      <button
        class="rounded-lg bg-brand-500 px-4 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600"
        @click="emit('close')"
      >
        关闭
      </button>
    </div>
  </n-modal>

  <!-- 编辑收藏 -->
  <n-modal
    :show="!!editing"
    preset="card"
    title="编辑收藏"
    style="width: 440px"
    @update:show="(v: boolean) => !v && (editing = null)"
  >
    <div class="mb-3">
      <label class="mb-1.5 block text-[12px] text-muted">标题</label>
      <n-input v-model:value="editForm.title" :maxlength="40" />
    </div>
    <div class="mb-4">
      <label class="mb-1.5 block text-[12px] text-muted">备注</label>
      <n-input v-model:value="editForm.note" type="textarea" :maxlength="200" :rows="3" placeholder="添加个人备注…" />
    </div>
    <div class="flex justify-end gap-2">
      <button
        class="rounded-lg border border-line px-4 py-1.5 text-[13px] text-muted transition-colors hover:text-ink"
        @click="editing = null"
      >
        取消
      </button>
      <button
        class="rounded-lg bg-brand-500 px-4 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600"
        @click="saveEdit"
      >
        保存
      </button>
    </div>
  </n-modal>
</template>
