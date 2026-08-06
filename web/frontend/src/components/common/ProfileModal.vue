<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { NModal, NInput, useMessage } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'

/**
 * 个人资料弹窗（原样迁移旧版功能）：头像色选择 + 自定义头像上传 + 显示名称 + 个人简介。
 * 保存后写入 auth store，persist 插件自动持久化。
 */

const AVATAR_COLORS = ['#1a5fb4', '#2ec27e', '#e5a50a', '#c061cb', '#e01b24', '#3584e4', '#986a44', '#33d17a']
const MAX_AVATAR_MB = 1

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const auth = useAuthStore()
const toast = useMessage()

const form = reactive({ displayName: '', bio: '', avatarColor: AVATAR_COLORS[0], avatarData: null as string | null })

// 每次打开时从 auth store 初始化表单
watch(
  () => props.show,
  (open) => {
    if (!open) return
    const p = auth.profile
    form.displayName = p?.displayName || ''
    form.bio = p?.bio || ''
    form.avatarColor = p?.avatarColor || AVATAR_COLORS[0]
    form.avatarData = p?.avatarData || null
  },
)

const fileInput = ref<HTMLInputElement | null>(null)

/** 上传自定义头像：图片转 dataURL（≤1MB），超出提示 */
function onAvatarFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  if (!file.type.startsWith('image/')) {
    toast.warning('请选择图片文件')
    return
  }
  if (file.size > MAX_AVATAR_MB * 1024 * 1024) {
    toast.warning(`图片不能超过 ${MAX_AVATAR_MB}MB`)
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    form.avatarData = String(reader.result)
  }
  reader.readAsDataURL(file)
}

function save() {
  auth.updateProfile({
    displayName: form.displayName.trim(),
    bio: form.bio.trim(),
    avatarColor: form.avatarColor,
    avatarData: form.avatarData,
  })
  toast.success('个人资料已保存')
  emit('close')
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="个人资料"
    style="width: 460px"
    @update:show="(v: boolean) => !v && emit('close')"
  >
    <!-- 预览 -->
    <div class="mb-4 flex items-center gap-3">
      <div
        class="flex h-14 w-14 items-center justify-center rounded-full text-lg font-semibold text-white"
        :style="{ backgroundColor: form.avatarColor }"
      >
        <img v-if="form.avatarData" :src="form.avatarData" class="h-full w-full rounded-full object-cover" alt="头像" />
        <span v-else>{{ (form.displayName || auth.username || 'U').slice(0, 2) }}</span>
      </div>
      <div>
        <div class="text-[15px] font-semibold text-ink">{{ form.displayName || '未设置昵称' }}</div>
        <div class="text-[12px] text-muted">@{{ auth.username }}</div>
      </div>
    </div>

    <!-- 头像颜色 -->
    <div class="mb-3">
      <label class="mb-1.5 block text-[12px] text-muted">头像颜色</label>
      <div class="flex flex-wrap gap-2">
        <button
          v-for="c in AVATAR_COLORS" :key="c"
          class="h-7 w-7 rounded-full transition-transform"
          :class="form.avatarColor === c ? 'scale-110 ring-2 ring-brand-400 ring-offset-1' : 'hover:scale-105'"
          :style="{ backgroundColor: c }"
          @click="form.avatarColor = c"
        />
      </div>
    </div>

    <!-- 自定义头像 -->
    <div class="mb-3">
      <label class="mb-1.5 block text-[12px] text-muted">自定义头像（可选）</label>
      <div class="flex items-center gap-2">
        <button
          class="rounded-lg border border-line bg-page px-3 py-1.5 text-[12px] text-ink transition-colors hover:border-brand-400"
          @click="fileInput?.click()"
        >
          上传图片
        </button>
        <input ref="fileInput" type="file" accept="image/*" class="hidden" @change="onAvatarFile" />
        <button
          v-if="form.avatarData"
          class="text-[12px] text-muted hover:text-ink"
          @click="form.avatarData = null"
        >
          移除
        </button>
      </div>
    </div>

    <!-- 显示名称 -->
    <div class="mb-3">
      <label class="mb-1.5 block text-[12px] text-muted">显示名称</label>
      <n-input v-model:value="form.displayName" :maxlength="20" placeholder="设置显示名称" />
    </div>

    <!-- 个人简介 -->
    <div class="mb-4">
      <label class="mb-1.5 block text-[12px] text-muted">个人简介（可选）</label>
      <n-input v-model:value="form.bio" type="textarea" :maxlength="100" :rows="2" placeholder="一句话介绍自己" />
    </div>

    <div class="flex justify-end gap-2">
      <button
        class="rounded-lg border border-line px-4 py-1.5 text-[13px] text-muted transition-colors hover:text-ink"
        @click="emit('close')"
      >
        取消
      </button>
      <button
        class="rounded-lg bg-brand-500 px-4 py-1.5 text-[13px] font-medium text-white transition-colors hover:bg-brand-600"
        @click="save"
      >
        保存
      </button>
    </div>
  </n-modal>
</template>
