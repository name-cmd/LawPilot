<script setup lang="ts">
import { NModal, NButton, NCard } from 'naive-ui'

/**
 * 隐私确认弹窗：输入内容含手机号等个人信息时，
 * 后端返回 privacy_confirm_required，前端弹窗征得用户同意后带 privacy_confirmed=true 重发。
 */
defineProps<{
  show: boolean
  message: string
}>()

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()
</script>

<template>
  <n-modal :show="show" preset="card" class="w-[420px]" title="隐私信息确认">
    <div class="text-sm leading-relaxed text-ink">
      <p class="mb-3">您的问题中包含可能涉及个人隐私的信息：</p>
      <div class="mb-4 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-[13px] text-ink">
        {{ message }}
      </div>
      <p class="mb-4 text-[13px] text-muted">
        确认发送后，内容将用于法律分析。您可以选择取消并修改问题。
      </p>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="emit('cancel')">取消</n-button>
        <n-button type="primary" @click="emit('confirm')">确认发送</n-button>
      </div>
    </template>
  </n-modal>
</template>
