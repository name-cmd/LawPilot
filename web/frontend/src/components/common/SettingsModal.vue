<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NModal, NSelect, NInput, NButton, NSwitch, useMessage, useDialog } from 'naive-ui'
import { useSettingsStore } from '@/stores/settings'
import { useModelsStore } from '@/stores/models'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useFavoritesStore } from '@/stores/favorites'
import { fetchUserProfile, saveUserProfile, clearUserData } from '@/api/user'
import { changePassword } from '@/api/auth'
import { isApiError } from '@/api/client'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()

const settings = useSettingsStore()
const models = useModelsStore()
const auth = useAuthStore()
const sessions = useSessionsStore()
const favorites = useFavoritesStore()
const toast = useMessage()
const dialog = useDialog()

// ── 问答偏好 ──────────────────────────────────────────────
const sampleOptions = [
  { label: '2 次（较快）', value: 2 },
  { label: '3 次（均衡）', value: 3 },
  { label: '5 次（最准）', value: 5 },
]

// ── 模型与 API Key ────────────────────────────────────────
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
    toast.success(p.api_key ? '已保存，本账号将使用该 Key' : '已清空，恢复使用服务端 Key')
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

// ── 账户：修改密码 ────────────────────────────────────────
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

// ── 账户：清空全部个人数据 ────────────────────────────────
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
        // 清本地数据 state（不能调 auth.$reset()，否则会把用户登出）
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

// ── 关于：系统信息 ────────────────────────────────────────
const health = ref<{ status: string; laws_loaded: boolean } | null>(null)

watch(
  () => props.show,
  async (v) => {
    if (!v) return
    try {
      const res = await fetch('/api/health')
      health.value = await res.json()
    } catch {
      health.value = null
    }
  },
)
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    title="设置"
    style="width: 480px"
    :bordered="false"
    @close="emit('close')"
    @update:show="(v: boolean) => !v && emit('close')"
  >
    <div class="space-y-6">
      <!-- 问答偏好 -->
      <div>
        <div class="mb-2 text-[13px] font-semibold text-ink">问答偏好</div>
        <div class="space-y-3">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px]">引用核验（NLI）</div>
              <div class="text-[11px] text-muted">隐性论断逻辑支撑</div>
            </div>
            <n-switch v-model:value="settings.enableNli" size="small" />
          </div>
          <div class="flex items-center justify-between">
            <div>
              <div class="text-[13px]">自一致性采样次数</div>
              <div class="text-[11px] text-muted">次数越多越准，回答更慢</div>
            </div>
            <n-select
              v-model:value="settings.nConsistencySamples"
              :options="sampleOptions"
              size="small"
              style="width: 130px"
            />
          </div>
        </div>
      </div>

      <!-- 模型与 API Key -->
      <div>
        <div class="mb-2 text-[13px] font-semibold text-ink">模型与 API Key</div>
        <div class="space-y-3">
          <n-select
            v-model:value="settings.globalDefaultModel"
            :options="modelOptions"
            :loading="models.loading"
            placeholder="选择默认模型"
            size="small"
          />
          <div class="flex gap-2">
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
      </div>

      <!-- 账户 -->
      <div>
        <div class="mb-2 text-[13px] font-semibold text-ink">账户</div>
        <div class="space-y-3">
          <template v-if="!showPwdForm">
            <n-button size="small" block @click="showPwdForm = true">修改密码</n-button>
          </template>
          <template v-else>
            <n-input
              v-model:value="oldPwd"
              type="password"
              show-password-on="click"
              placeholder="原密码"
              size="small"
            />
            <n-input
              v-model:value="newPwd"
              type="password"
              show-password-on="click"
              placeholder="新密码（至少 6 位）"
              size="small"
            />
            <n-input
              v-model:value="confirmPwd"
              type="password"
              show-password-on="click"
              placeholder="确认新密码"
              size="small"
            />
            <div class="flex gap-2">
              <n-button size="small" type="primary" :loading="changingPwd" @click="submitPassword">确认修改</n-button>
              <n-button size="small" @click="showPwdForm = false">取消</n-button>
            </div>
          </template>

          <n-button size="small" block type="error" :loading="clearing" @click="confirmClear">
            清空全部个人数据
          </n-button>
        </div>
      </div>

      <!-- 关于 -->
      <div>
        <div class="mb-2 text-[13px] font-semibold text-ink">关于</div>
        <div class="space-y-1.5 text-[12px] text-muted">
          <div class="flex justify-between">
            <span>当前账号</span>
            <span class="text-ink">{{ auth.displayLabel }}</span>
          </div>
          <div class="flex justify-between">
            <span>可用模型</span>
            <span class="text-ink">{{ models.apiModels.length }} 个</span>
          </div>
          <div class="flex justify-between">
            <span>离线引擎</span>
            <span class="text-ink">{{ models.localEngine?.available ? '可用' : '未启用' }}</span>
          </div>
          <div class="flex justify-between">
            <span>服务状态</span>
            <span class="text-ink">
              {{ health ? (health.status === 'ok' ? '正常' : '降级') + (health.laws_loaded ? ' · 法律库已加载' : '') : '获取中…' }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </n-modal>
</template>
