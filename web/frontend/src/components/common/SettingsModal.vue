<script setup lang="ts">
import { computed } from 'vue'
import { NModal, NSelect, NText } from 'naive-ui'
import { useSettingsStore } from '@/stores/settings'
import { useModelsStore } from '@/stores/models'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const settings = useSettingsStore()
const models = useModelsStore()

/** 可选的默认模型列表（仅 API 模型；离线引擎不可作为全局默认） */
const modelOptions = computed(() =>
  models.enabledModels.map((m) => ({
    label: m.display_name,
    value: m.id,
  })),
)

/** 当前默认模型的补充说明（价格/能力） */
const currentDefault = computed(
  () => models.apiModels.find((m) => m.id === settings.globalDefaultModel) ?? null,
)
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="设置"
    style="width: 420px"
    :bordered="false"
    @close="emit('close')"
    @update:show="(v: boolean) => !v && emit('close')"
  >
    <div class="space-y-4">
      <!-- 全局默认模型：Auto 跟随它 -->
      <div>
        <div class="mb-1.5 text-[13px] font-medium text-ink">全局默认模型</div>
        <n-select
          v-model:value="settings.globalDefaultModel"
          :options="modelOptions"
          :loading="models.loading"
          placeholder="选择默认模型"
          size="small"
        />
        <n-text v-if="currentDefault" depth="3" class="mt-1.5 block text-[11px]">
          {{ currentDefault.price_tier }}；{{ currentDefault.capabilities }}
        </n-text>
      </div>

      <div class="rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-muted dark:bg-slate-800">
        「Auto」选项会跟随此处设置的全局默认模型；也可随时在输入框旁的模型选择器中切换具体模型，切换对当前会话生效。
      </div>
    </div>
  </n-modal>
</template>
