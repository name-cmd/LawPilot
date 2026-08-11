<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  NModal,
  NSelect,
  NInput,
  NButton,
  NSwitch,
  NRadioGroup,
  NRadioButton,
  NCheckbox,
  useMessage,
  useDialog,
} from 'naive-ui'
import {
  SettingsOutline,
  DesktopOutline,
  HardwareChipOutline,
  SearchOutline,
  ShieldCheckmarkOutline,
  LockClosedOutline,
  CloudDownloadOutline,
  WarningOutline,
  ChevronForwardOutline,
} from '@vicons/ionicons5'
import { useSettingsStore } from '@/stores/settings'
import { useModelsStore } from '@/stores/models'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useFavoritesStore } from '@/stores/favorites'
import { fetchUserProfile, saveUserProfile, clearUserData } from '@/api/user'
import { changePassword } from '@/api/auth'
import { isApiError } from '@/api/client'
import type { TrustDimensionConfig } from '@/stores/settings'

type SectionKey = 'general' | 'model' | 'retrieval' | 'trust' | 'privacy' | 'data'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const settings = useSettingsStore()
const models = useModelsStore()
const auth = useAuthStore()
const sessions = useSessionsStore()
const favorites = useFavoritesStore()
const toast = useMessage()
const dialog = useDialog()

const activeSection = ref<SectionKey>('general')

const sections: { key: SectionKey; label: string; icon: typeof SettingsOutline }[] = [
  { key: 'general', label: '通用', icon: DesktopOutline },
  { key: 'model', label: '模型与推理', icon: HardwareChipOutline },
  { key: 'retrieval', label: '检索与引用', icon: SearchOutline },
  { key: 'trust', label: '可信评估', icon: ShieldCheckmarkOutline },
  { key: 'privacy', label: '隐私与安全', icon: LockClosedOutline },
  { key: 'data', label: '数据管理', icon: CloudDownloadOutline },
]

// ── 通用 ──────────────────────────────────────────────────
const themeOptions = [
  { label: '浅色', value: 'light' },
  { label: '深色', value: 'dark' },
  { label: '跟随系统', value: 'system' },
]

const fontSizeOptions = [
  { label: '标准', value: 'standard' },
  { label: '偏大', value: 'large' },
  { label: '超大', value: 'xlarge' },
]

watch(
  () => settings.fontSize,
  () => settings.applyFontSize(),
  { immediate: true },
)

// ── 模型与推理 ────────────────────────────────────────────
const apiKeyInput = ref('')
const savingKey = ref(false)

const modelOptions = computed(() =>
  models.enabledModels.map((m) => ({
    label: m.display_name,
    value: m.id,
  })),
)

watch(
  () => props.show,
  async (v) => {
    if (!v) return
    activeSection.value = 'general'
    if (!auth.token) return
    try {
      const p = await fetchUserProfile(auth.token)
      apiKeyInput.value = p.api_key || ''
    } catch {
      apiKeyInput.value = ''
    }
  },
)

async function saveApiKey() {
  if (!auth.token) return
  savingKey.value = true
  try {
    const p = await saveUserProfile(auth.token, { api_key: apiKeyInput.value.trim() })
    apiKeyInput.value = p.api_key || ''
    toast.success(p.api_key ? '已保存，本账号将使用该 Key' : '已清空，恢复使用服务端 Key')
  } catch (e) {
    toast.error(isApiError(e) ? e.message : '保存失败，请检查服务是否在线')
  } finally {
    savingKey.value = false
  }
}

// ── 检索与引用 ────────────────────────────────────────────
const sampleOptions = [
  { label: '2 次（较快）', value: 2 },
  { label: '3 次（均衡）', value: 3 },
  { label: '5 次（最准）', value: 5 },
]

const citationStyleOptions = [
  { label: '简洁', value: 'concise' },
  { label: '完整', value: 'full' },
]

// ── 可信评估 ──────────────────────────────────────────────
function toggleDimension(dim: TrustDimensionConfig) {
  settings.toggleTrustDimension(dim.key)
}

// ── 隐私与安全：修改密码 ──────────────────────────────────
const showPwdForm = ref(false)
const oldPwd = ref('')
const newPwd = ref('')
const confirmPwd = ref('')
const changingPwd = ref(false)

async function submitPassword() {
  if (newPwd.value.length < 6) {
    toast.warning('新密码至少 6 位')
    return
  }
  if (newPwd.value !== confirmPwd.value) {
    toast.warning('两次输入的新密码不一致')
    return
  }
  if (!auth.token) return
  changingPwd.value = true
  try {
    const r = await changePassword(auth.token, oldPwd.value, newPwd.value)
    toast.success(r.revoked_devices > 0 ? `密码已修改，${r.revoked_devices} 台其他设备已下线` : '密码已修改')
    oldPwd.value = newPwd.value = confirmPwd.value = ''
    showPwdForm.value = false
  } catch (e) {
    toast.error(isApiError(e) ? e.message : '修改失败，请重试')
  } finally {
    changingPwd.value = false
  }
}

// ── 数据管理：导出与清空 ──────────────────────────────────
function exportUserData() {
  const payload = {
    exportedAt: new Date().toISOString(),
    username: auth.username,
    sessions: sessions.sessions,
    favorites: favorites.favorites,
    settings: {
      theme: settings.theme,
      fontSize: settings.fontSize,
      globalDefaultModel: settings.globalDefaultModel,
      citationStyle: settings.citationStyle,
    },
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `lawtrust-backup-${auth.username || 'guest'}-${Date.now()}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  toast.success('已开始下载备份文件')
}

const clearing = ref(false)

function confirmClear() {
  if (!auth.token) return
  dialog.warning({
    title: '清空全部个人数据',
    content: '将清空本账号的全部会话记录、收藏与个人资料（保留账号与 API Key）。此操作不可恢复，确定继续？',
    positiveText: '清空',
    negativeText: '取消',
    onPositiveClick: async () => {
      clearing.value = true
      try {
        await clearUserData(auth.token!)
        sessions.$reset()
        sessions.ensureSession()
        favorites.$reset()
        auth.updateProfile({ displayName: '', bio: '', avatarColor: '', avatarData: null })
        toast.success('已清空全部个人数据')
      } catch (e) {
        toast.error(isApiError(e) ? e.message : '清空失败，请重试')
      } finally {
        clearing.value = false
      }
    },
  })
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="设置"
    style="width: 720px"
    :bordered="false"
    @close="emit('close')"
    @update:show="(v: boolean) => !v && emit('close')"
  >
    <div class="flex h-[520px]">
      <!-- 左侧导航 -->
      <div
        class="flex w-44 flex-col gap-1 border-r border-line bg-surface-soft/50 px-3 py-4"
      >
        <button
          v-for="s in sections"
          :key="s.key"
          class="flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] transition-colors"
          :class="
            activeSection === s.key
              ? 'bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-400'
              : 'text-muted hover:bg-surface-soft hover:text-ink'
          "
          @click="activeSection = s.key"
        >
          <component :is="s.icon" class="h-4 w-4" />
          <span>{{ s.label }}</span>
          <chevron-forward-outline v-if="activeSection === s.key" class="ml-auto h-3.5 w-3.5 opacity-60" />
        </button>
      </div>

      <!-- 右侧内容 -->
      <div class="flex-1 overflow-y-auto px-7 py-5">
        <!-- 通用 -->
        <div v-if="activeSection === 'general'" class="space-y-5">
          <h3 class="text-[15px] font-medium text-ink">通用</h3>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">外观</div>
              <div class="text-[12px] text-muted">切换浅色、深色或跟随系统</div>
            </div>
            <n-radio-group v-model:value="settings.theme" size="small" @update:value="settings.applyTheme()">
              <n-radio-button
                v-for="opt in themeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </n-radio-group>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">字体大小</div>
              <div class="text-[12px] text-muted">调整界面与回答正文字号</div>
            </div>
            <n-radio-group v-model:value="settings.fontSize" size="small">
              <n-radio-button
                v-for="opt in fontSizeOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </n-radio-group>
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">界面语言</div>
              <div class="text-[12px] text-muted">当前仅支持简体中文</div>
            </div>
            <n-select
              v-model:value="settings.language"
              disabled
              size="small"
              style="width: 120px"
              :options="[{ label: '简体中文', value: 'zh-CN' }]"
            />
          </div>
        </div>

        <!-- 模型与推理 -->
        <div v-if="activeSection === 'model'" class="space-y-5">
          <h3 class="text-[15px] font-medium text-ink">模型与推理</h3>

          <div>
            <div class="text-[13px] font-medium text-ink">默认模型</div>
            <div class="text-[12px] text-muted">发送框选择“Auto”时将使用此处指定的模型</div>
            <n-select
              v-model:value="settings.globalDefaultModel"
              :options="modelOptions"
              :loading="models.loading"
              placeholder="选择默认模型"
              size="small"
              class="mt-2"
            />
          </div>

          <div>
            <div class="text-[13px] font-medium text-ink">自配 API Key</div>
            <div class="text-[12px] text-muted">留空则使用服务端默认 Key</div>
            <div class="mt-2 flex gap-2">
              <n-input
                v-model:value="apiKeyInput"
                type="password"
                show-password-on="click"
                placeholder="sk-*******"
                size="small"
              />
              <n-button size="small" type="primary" :loading="savingKey" :disabled="!auth.token" @click="saveApiKey">
                保存
              </n-button>
            </div>
          </div>

          <div class="flex items-center justify-between border-t border-line pt-4">
            <div>
              <div class="text-[13px] text-ink">深度思考模式</div>
              <div class="text-[12px] text-muted">适合复杂法律推理，响应会更慢</div>
            </div>
            <n-switch v-model:value="settings.thinkingMode" size="small" />
          </div>
        </div>

        <!-- 检索与引用 -->
        <div v-if="activeSection === 'retrieval'" class="space-y-5">
          <h3 class="text-[15px] font-medium text-ink">检索与引用</h3>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">启用知识库检索（RAG）</div>
              <div class="text-[12px] text-muted">关闭后仅依赖模型内置知识</div>
            </div>
            <n-switch v-model:value="settings.useRag" size="small" />
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">引用核验（NLI）</div>
              <div class="text-[12px] text-muted">隐性论断与法条原文逻辑比对</div>
            </div>
            <n-switch v-model:value="settings.enableNli" size="small" />
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">自一致性采样次数</div>
              <div class="text-[12px] text-muted">次数越多越准，回答更慢</div>
            </div>
            <n-select
              v-model:value="settings.nConsistencySamples"
              :options="sampleOptions"
              size="small"
              style="width: 130px"
            />
          </div>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">引用展示风格</div>
              <div class="text-[12px] text-muted">控制回答中法条引用的详细程度</div>
            </div>
            <n-radio-group v-model:value="settings.citationStyle" size="small">
              <n-radio-button
                v-for="opt in citationStyleOptions"
                :key="opt.value"
                :value="opt.value"
                :label="opt.label"
              />
            </n-radio-group>
          </div>
        </div>

        <!-- 可信评估 -->
        <div v-if="activeSection === 'trust'" class="space-y-5">
          <h3 class="text-[15px] font-medium text-ink">可信评估</h3>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">启用六维可信评估</div>
              <div class="text-[12px] text-muted">回答右侧展示 TrustLLM 雷达图与评分</div>
            </div>
            <n-switch v-model:value="settings.enableTrustEval" size="small" />
          </div>

          <div class="rounded-lg bg-surface-soft p-4">
            <div class="mb-3 text-[12px] text-muted">评估维度（关闭后该维度在雷达图中隐藏）</div>
            <div class="grid grid-cols-2 gap-3">
              <label
                v-for="dim in settings.trustDimensions"
                :key="dim.key"
                class="flex cursor-pointer items-center gap-2 text-[13px] text-ink"
              >
                <n-checkbox
                  :checked="dim.enabled"
                  :disabled="!settings.enableTrustEval"
                  @update:checked="toggleDimension(dim)"
                />
                {{ dim.label }}
              </label>
            </div>
          </div>
        </div>

        <!-- 隐私与安全 -->
        <div v-if="activeSection === 'privacy'" class="space-y-5">
          <h3 class="text-[15px] font-medium text-ink">隐私与安全</h3>

          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px] text-ink">检测到敏感信息时主动提示</div>
              <div class="text-[12px] text-muted">输入守卫发现身份证号、手机号等隐私内容时提醒</div>
            </div>
            <n-switch v-model:value="settings.privacyAlert" size="small" />
          </div>

          <div class="rounded-lg border border-line p-4">
            <div class="mb-3 text-[13px] font-medium text-ink">修改密码</div>
            <template v-if="!showPwdForm">
              <n-button size="small" block @click="showPwdForm = true">修改密码</n-button>
            </template>
            <template v-else>
              <div class="space-y-2">
                <n-input v-model:value="oldPwd" type="password" show-password-on="click" placeholder="原密码" size="small" />
                <n-input v-model:value="newPwd" type="password" show-password-on="click" placeholder="新密码（至少 6 位）" size="small" />
                <n-input v-model:value="confirmPwd" type="password" show-password-on="click" placeholder="确认新密码" size="small" />
                <div class="flex gap-2 pt-1">
                  <n-button size="small" type="primary" :loading="changingPwd" @click="submitPassword">
                    确认修改
                  </n-button>
                  <n-button size="small" @click="showPwdForm = false">取消</n-button>
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- 数据管理 -->
        <div v-if="activeSection === 'data'" class="space-y-5">
          <h3 class="text-[15px] font-medium text-ink">数据管理</h3>

          <div class="flex items-center justify-between rounded-lg border border-line p-4">
            <div>
              <div class="text-[13px] font-medium text-ink">导出会话与收藏</div>
              <div class="text-[12px] text-muted">下载 JSON 备份到本地</div>
            </div>
            <n-button size="small" @click="exportUserData">导出</n-button>
          </div>

          <div class="rounded-lg border border-danger/30 bg-danger/5 p-4 dark:bg-danger/10">
            <div class="flex items-center justify-between">
              <div>
                <div class="text-[13px] font-medium text-danger">清空全部个人数据</div>
                <div class="text-[12px] text-muted">会话、收藏、个人资料将被删除，不可恢复</div>
              </div>
              <n-button size="small" type="error" :loading="clearing" @click="confirmClear">
                清空
              </n-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </n-modal>
</template>
