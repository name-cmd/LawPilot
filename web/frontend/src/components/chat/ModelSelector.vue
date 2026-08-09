<script setup lang="ts">
import { computed } from 'vue'
import { NIcon, NPopover } from 'naive-ui'
import { ChevronDownOutline, CubeOutline, LockClosedOutline, SparklesOutline } from '@vicons/ionicons5'
import { useSettingsStore } from '@/stores/settings'
import { useModelsStore } from '@/stores/models'
import { brandOf, imgError, logoUrl, modelLogo } from '@/utils/modelLogo'

const settings = useSettingsStore()
const models = useModelsStore()

/** 触发器按钮的当前选择摘要（如 `Auto` / `Qwen3.7 Max` / `离线调用`） */
const summary = computed(() => {
  if (settings.modelProvider === 'local') return '离线调用'
  if (settings.apiModel === 'auto') return 'Auto'
  const m = models.apiModels.find((x) => x.id === settings.apiModel)
  return m?.display_name ?? settings.apiModel
})

/** 离线引擎就绪状态 */
const localReady = computed(() => models.localEngine?.available ?? false)
const localReason = computed(() => models.localEngine?.reason ?? '正在检测…')

/** 离线调用悬停提示：能力边界 + 未就绪原因（指南 8.2 文案） */
const localTip = computed(() => {
  if (!localReady.value) return `未就绪：${localReason.value}（需 CUDA GPU 与本地模型文件）`
  return '模型为 Qwen2.5-7B，参数量较小，效果不及 API 调用模型，推荐处理隐私数据时使用'
})

/** 当前选中项的供应商品牌：离线调用 → null（触发器显示锁图标）；Auto → null（显示专属星光标识）；否则当前模型 */
const currentBrand = computed(() => {
  if (settings.modelProvider === 'local') return null
  if (settings.apiModel === 'auto') return null
  return brandOf(settings.apiModel)
})
const currentLogoUrl = computed(() => logoUrl(currentBrand.value))

/** 面板打开时若目录未加载则补拉 */
function onPanelShow(show: boolean) {
  if (show && models.apiModels.length === 0 && !models.loading && !models.error) {
    models.fetchModels()
  }
}
</script>

<template>
  <n-popover trigger="click" placement="top-start" :width="360" arrow :show-arrow="false" @update:show="onPanelShow">
    <template #trigger>
      <!-- 当前选择摘要按钮（参考 DeepSeek：选择器悬浮在输入框上方） -->
      <button
        class="flex cursor-pointer items-center gap-1.5 rounded-full border border-line bg-slate-50 px-2.5 py-1 text-[11px] text-slate-600 transition-colors hover:border-blue-400 hover:bg-blue-50 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-300 dark:hover:bg-slate-600"
        title="选择模型"
      >
        <!-- 当前选中项标识：具体模型 → 品牌 logo；Auto → 星光标识；离线调用 → 锁图标 -->
        <img
          v-if="currentLogoUrl"
          :src="currentLogoUrl"
          class="h-3.5 w-3.5 shrink-0 rounded-full object-contain"
          @error="imgError"
        />
        <span
          v-else-if="settings.modelProvider === 'api'"
          class="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500"
        >
          <n-icon :component="SparklesOutline" size="9" class="text-white" />
        </span>
        <n-icon v-else :component="LockClosedOutline" size="13" />
        <span class="max-w-36 truncate">{{ summary }}</span>
        <n-icon :component="ChevronDownOutline" size="12" class="text-muted" />
      </button>
    </template>

    <div class="w-full">
      <!-- 第一级：引擎选择（离线调用 / API 调用，仅两个选项，无多余说明文字） -->
      <div class="mb-1 text-[11px] font-medium text-muted">引擎选择</div>
      <div class="mb-2 grid grid-cols-2 gap-2">
        <!-- 离线调用：未就绪时置灰；悬停提示用浏览器原生 tooltip（外层 div 的 title，
             disabled 按钮本身不触发 title，放在外层 div 上则悬停整个方框都会显示） -->
        <div class="relative" :title="localTip">
          <button
            :disabled="!localReady"
            class="flex w-full flex-col items-start gap-0.5 rounded-lg border px-2.5 py-2 text-left transition-colors cursor-pointer disabled:cursor-not-allowed"
            :class="
              settings.modelProvider === 'local'
                ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40'
                : 'border-line bg-white hover:border-blue-300 dark:bg-slate-800'
            + (localReady ? '' : ' opacity-45')
            "
            @click="settings.modelProvider = 'local'"
          >
            <span class="flex items-center gap-1 text-[12px] font-medium" :class="localReady ? 'text-ink' : 'text-slate-400'">
              <n-icon :component="LockClosedOutline" size="13" />
              离线调用
            </span>
          </button>
        </div>

        <!-- API 调用 -->
        <button
          class="flex cursor-pointer items-center gap-1 rounded-lg border px-2.5 py-2 text-left transition-colors"
          :class="
            settings.modelProvider === 'api'
              ? 'border-blue-400 bg-blue-50 dark:bg-blue-950/40'
              : 'border-line bg-white hover:border-blue-300 dark:bg-slate-800'
          "
          @click="settings.modelProvider = 'api'"
        >
          <n-icon :component="CubeOutline" size="13" />
          <span class="text-[12px] font-medium text-ink">API 调用</span>
        </button>
      </div>

      <!-- 第二级：API 下的模型列表（Auto + 注册表驱动；模型名下方不显示文字，
           悬停时通过 title 显示定位介绍） -->
      <template v-if="settings.modelProvider === 'api'">
        <div class="mb-1 text-[11px] font-medium text-muted">模型选择</div>
        <div class="max-h-60 space-y-0.5 overflow-y-auto pr-1">
          <!-- Auto：跟随全局默认（设置面板可改），定位说明放悬停提示 -->
          <button
            :title="`跟随全局默认（${models.defaultModelInfo?.display_name ?? '设置中配置'}），可在设置面板修改`"
            class="flex w-full cursor-pointer items-center rounded-md px-2 py-1.5 text-left transition-colors"
            :class="settings.apiModel === 'auto' ? 'bg-blue-50 dark:bg-blue-950/40' : 'hover:bg-slate-100 dark:hover:bg-slate-700/60'"
            @click="settings.apiModel = 'auto'"
          >
            <span class="flex min-w-0 items-center gap-1.5">
              <!-- Auto 专属标识：渐变圆底星光图标（代表「智能自动选择」），
                   不使用任何供应商 logo，避免与具体品牌绑定 -->
              <span class="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-400 to-purple-500">
                <n-icon :component="SparklesOutline" size="10" class="text-white" />
              </span>
              <span class="text-[12px] font-medium text-ink">Auto</span>
            </span>
          </button>

          <!-- 7 个模型：仅显示名称（+默认徽标），定位介绍放悬停提示 -->
          <button
            v-for="m in models.enabledModels"
            :key="m.id"
            :title="m.capabilities"
            class="flex w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left transition-colors"
            :class="settings.apiModel === m.id ? 'bg-blue-50 dark:bg-blue-950/40' : 'hover:bg-slate-100 dark:hover:bg-slate-700/60'"
            @click="settings.apiModel = m.id"
          >
            <span class="flex min-w-0 items-center gap-1.5">
              <!-- 供应商 logo（缺图时自动隐藏，仅显示模型名） -->
              <img
                v-if="modelLogo(m.id)"
                :src="modelLogo(m.id)"
                class="h-4 w-4 shrink-0 rounded-full object-contain"
                @error="imgError"
              />
              <span class="truncate text-[12px] font-medium text-ink">{{ m.display_name }}</span>
            </span>
            <span v-if="m.is_default" class="shrink-0 rounded bg-blue-100 px-1 py-0.5 text-[9px] text-blue-600 dark:bg-blue-900/50 dark:text-blue-300">默认</span>
          </button>
        </div>
      </template>

      <!-- 离线模式说明 -->
      <div v-else class="mt-1 rounded-md bg-slate-50 px-2.5 py-1.5 text-[10px] leading-relaxed text-muted dark:bg-slate-800">
        隐私模式：您的提问与上传文档仅在本机处理，不会发送给任何外部服务。
      </div>

      <!-- 目录加载失败提示 -->
      <div v-if="models.error" class="mt-1.5 text-[10px] text-red-400">模型目录加载失败：{{ models.error }}</div>
    </div>
  </n-popover>
</template>
