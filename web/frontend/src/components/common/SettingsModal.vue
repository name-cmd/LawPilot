<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NModal, NSelect, NText, NInput, NButton, useMessage } from 'naive-ui'
import { useSettingsStore } from '@/stores/settings'
import { useModelsStore } from '@/stores/models'
import { useAuthStore } from '@/stores/auth'
import { fetchUserProfile, saveUserProfile } from '@/api/user'
import { isApiError } from '@/api/client'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const settings = useSettingsStore()
const models = useModelsStore()
const auth = useAuthStore()
const toast = useMessage()

// ── 每用户 API Key（阶段三：存服务端，换设备登录自动恢复）────
const apiKeyInput = ref('')
const savingKey = ref(false)

// 打开设置面板时从服务端拉取该账号当前 Key（未登录/失败时留空展示）
watch(
  () => props.show,
  async (v) => {
    if (v && auth.token) {
      try {
        const p = await fetchUserProfile(auth.token)
        apiKeyInput.value = p.api_key || ''
      } catch {
        /* 服务端不可达：留空展示 */
      }
    }
  },
)

/** 保存 API Key：空串 = 清除，恢复使用服务端 .env Key */
async function saveApiKey() {
  if (!auth.token) return
  savingKey.value = true
  try {
    const p = await saveUserProfile(auth.token, { api_key: apiKeyInput.value.trim() })
    apiKeyInput.value = p.api_key || ''
    toast.success(p.api_key ? 'API Key 已保存，本账号后续问答将使用该 Key' : '已清空，本账号恢复使用服务端配置的 Key')
  } catch (e) {
    toast.error(isApiError(e) ? e.message : '保存失败，请检查服务是否在线')
  } finally {
    savingKey.value = false
  }
}

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
    style="width: 460px"
    :bordered="false"
    @close="emit('close')"
    @update:show="(v: boolean) => !v && emit('close')"
  >
    <div class="space-y-5">
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

      <!-- 每用户 API Key -->
      <div>
        <div class="mb-1.5 text-[13px] font-medium text-ink">API Key（阿里云百炼）</div>
        <div class="flex gap-2">
          <n-input
            v-model:value="apiKeyInput"
            type="password"
            show-password-on="click"
            placeholder="留空 = 使用服务端配置的 Key"
            size="small"
          />
          <n-button size="small" type="primary" :loading="savingKey" :disabled="!auth.token" @click="saveApiKey">
            保存
          </n-button>
        </div>
        <n-text depth="3" class="mt-1.5 block text-[11px] leading-relaxed">
          留空 = 使用服务端 .env 配置的 Key（root 默认）；填写 = 本账号所有问答使用自己的 Key（不填不会影响其他账号）。Key 仅存于服务端，换设备登录自动恢复。
        </n-text>
      </div>

      <div class="rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-muted dark:bg-slate-800">
        「Auto」选项会跟随此处设置的全局默认模型；也可随时在输入框旁的模型选择器中切换具体模型，切换对当前会话生效。
      </div>
    </div>
  </n-modal>
</template>
