<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { NModal, NButton, NInput } from 'naive-ui'

const props = defineProps<{ show: boolean; initial: string }>()
const emit = defineEmits<{ confirm: [title: string]; cancel: [] }>()

const title = ref('')
const inputRef = ref<InstanceType<typeof NInput> | null>(null)

watch(
  () => props.show,
  (v) => {
    if (v) {
      title.value = props.initial
      nextTick(() => inputRef.value?.focus())
    }
  },
)

function confirm() {
  emit('confirm', title.value)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') {
    e.preventDefault()
    confirm()
  }
  if (e.key === 'Escape') emit('cancel')
}
</script>

<template>
  <n-modal :show="show" preset="card" class="w-[400px]" title="重命名会话" @update:show="(v) => !v && emit('cancel')">
    <n-input
      ref="inputRef"
      v-model:value="title"
      placeholder="输入新的会话名称"
      maxlength="50"
      show-count
      @keydown="onKeydown"
    />
    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button @click="emit('cancel')">取消</n-button>
        <n-button type="primary" :disabled="!title.trim()" @click="confirm">保存</n-button>
      </div>
    </template>
  </n-modal>
</template>
