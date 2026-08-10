<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NIcon, NModal, NCheckbox } from 'naive-ui'
import { PersonOutline, KeyOutline, EyeOutline, EyeOffOutline } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { useSessionsStore } from '@/stores/sessions'
import { useFavoritesStore } from '@/stores/favorites'
import { useSync } from '@/composables/useSync'
import { isApiError } from '@/api/client'

const router = useRouter()
const auth = useAuthStore()
const sessions = useSessionsStore()
const favorites = useFavoritesStore()

// 登录 / 注册 两种模式（注册：用户名+密码+确认密码，成功自动登录）
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const confirmPassword = ref('')
const loading = ref(false)
const errorMsg = ref('')

// 记住密码：勾选后账号密码明文存 localStorage，下次打开自动回填。
// 测试阶段固定账号可接受；生产环境应改用 HttpOnly cookie / 加密存储，避免明文落盘。
const REMEMBER_KEY = 'lawtrust_remember'
const rememberMe = ref(false)
const showPassword = ref(false)

onMounted(() => {
  // 打开登录页时回填上次「记住密码」的账号
  try {
    const saved = JSON.parse(localStorage.getItem(REMEMBER_KEY) || 'null')
    if (saved?.username) {
      username.value = saved.username
      if (saved.password) password.value = saved.password
      rememberMe.value = saved.remember === true
    }
  } catch {
    localStorage.removeItem(REMEMBER_KEY)
  }
})

// 法律协议弹窗（交互与旧版一致：欢迎弹窗 + 三个文档链接 + 勾选后按钮才可用）
const agreementShow = ref(false)
const agreementChecked = ref(false)

// 协议文档弹窗
const LEGAL_DOCS: Record<string, { title: string; body: string }> = {
  user: {
    title: '用户协议',
    body:
      '一、本平台基于大语言模型与法律知识库生成回答，内容仅供学习与参考，不构成正式法律意见。\n' +
      '二、涉及重大权益事项（诉讼、仲裁、大额合同等），请咨询执业律师。\n' +
      '三、请勿将平台内容用于非法用途或损害他人权益。',
  },
  privacy: {
    title: '隐私政策',
    body:
      '一、您提交的问题与文档将仅用于法律分析与检索增强，不作他用。\n' +
      '二、敏感个人信息（身份证号、银行卡号等）提交时将自动脱敏处理。\n' +
      '三、请勿上传与您本人无关的他人隐私信息。',
  },
  ai: {
    title: 'AI 咨询非正式法律意见声明',
    body:
      '一、AI 生成内容可能存在不准确或过时之处，法律法规以官方发布文本为准。\n' +
      '二、引用法条会进行核验与可信度评估，但仍建议核对官方原文。\n' +
      '三、因模型生成内容不准确导致的任何损失，平台不承担责任。',
  },
}
const docShow = ref(false)
const docTitle = ref('')
const docBody = ref('')

function openLegalDoc(key: string) {
  const doc = LEGAL_DOCS[key]
  if (!doc) return
  docTitle.value = doc.title
  docBody.value = doc.body
  docShow.value = true
}

/** 登录/注册模式的提交入口：登录走协议弹窗，注册直接校验并提交 */
function handleSubmit() {
  errorMsg.value = ''
  if (mode.value === 'register') {
    performRegister()
    return
  }
  if (!username.value.trim() || !password.value) {
    errorMsg.value = '请输入用户名和密码'
    return
  }
  agreementChecked.value = false
  agreementShow.value = true
}

/** 登录成功后统一的收尾：加载该用户本地数据 → 从服务端同步恢复 → 进聊天页 */
async function afterLogin() {
  await sessions.loadForCurrentUser()
  favorites.loadForCurrentUser()
  // 双写同步拉取：服务端有数据则以服务端为准（换设备恢复）；首次登录则回写本地数据
  await useSync().pull()
  password.value = ''
  router.push('/')
}

async function performLogin() {
  agreementShow.value = false
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    // 记住密码：登录成功才写入；未勾选则清除历史记录
    if (rememberMe.value) {
      localStorage.setItem(
        REMEMBER_KEY,
        JSON.stringify({
          username: username.value.trim(),
          password: password.value,
          remember: true,
        }),
      )
    } else {
      localStorage.removeItem(REMEMBER_KEY)
    }
    await afterLogin()
  } catch (e) {
    errorMsg.value = isApiError(e) ? e.message : '登录失败，请重试'
  } finally {
    loading.value = false
  }
}

/** 注册（规则与后端 user_store.py 保持一致，前端先拦一道） */
async function performRegister() {
  const name = username.value.trim()
  if (!/^[A-Za-z_][A-Za-z0-9_]{2,19}$/.test(name)) {
    errorMsg.value = '用户名需为 3-20 位字母/数字/下划线（以字母或下划线开头）'
    return
  }
  if (password.value.length < 6) {
    errorMsg.value = '密码至少 6 位'
    return
  }
  if (password.value !== confirmPassword.value) {
    errorMsg.value = '两次输入的密码不一致'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.register(name, password.value)
    await afterLogin()
  } catch (e) {
    // 409 冲突 / 400 校验错误：后端返回的中文 detail 直接展示
    errorMsg.value = isApiError(e) ? e.message : '注册失败，请重试'
  } finally {
    loading.value = false
  }
}

/** 登录/注册模式切换：清空错误与确认密码 */
function switchMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  errorMsg.value = ''
  confirmPassword.value = ''
}
</script>

<template>
  <!-- 浅色背景图 sign1.png（右侧近白斜切留白区承载登录卡片）：
       bg-cover 随屏幕自适应缩放，不再加深色渐变遮罩（浅色图叠加深色遮罩会发灰） -->
  <div
    class="relative flex min-h-screen w-full items-center justify-center sm:justify-end"
    style="background-image: url('/figure/sign1.png'); background-size: cover; background-position: center"
  >
    <!-- 登录卡片：右侧对齐（pr 留白），白底/微透明白 + 圆角阴影 -->
    <div class="w-full max-w-[500px] pr-0 py-10 sm:pr-12 lg:pr-24">
      <!-- 品牌标语：位于登录卡片外侧上方（页面级 Header），与卡片同宽右对齐 -->
      <p class="mb-5 text-center text-2xl font-bold tracking-wide text-blue-900">法信通 · 可信的法律智能问答平台</p>
      <div class="rounded-2xl border border-slate-100 bg-white/95 p-12 shadow-xl backdrop-blur-sm animate-fade-in-up">
        <h1 class="mb-10 text-2xl text-center font-bold text-blue-900">
          {{ mode === 'login' ? '用户登录' : '注册新账号' }}
        </h1>

        <!-- 错误提示 -->
        <p
          v-if="errorMsg"
          class="mb-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-600"
        >
          {{ errorMsg }}
        </p>

        <form class="space-y-8" @submit.prevent="handleSubmit">
          <!-- 用户名：图标与输入框共用一个带边框的 flex 容器（focus-within 触发紫色光圈），
               图标和输入框是同一方框内的两个子元素，任何环境下都不可能跑到方框外面 -->
          <div class="flex items-center rounded-lg border border-slate-200 bg-white transition-all focus-within:border-blue-600 focus-within:ring-2 focus-within:ring-blue-500/20">
            <n-icon :component="PersonOutline" size="18" class="ml-4 shrink-0 text-slate-400" />
            <input
              v-model="username"
              type="text"
              placeholder="用户名"
              autocomplete="username"
              class="w-full min-w-0 flex-1 rounded-lg bg-transparent py-4 pl-3 pr-4 text-sm text-slate-800 outline-none placeholder:text-slate-400"
            />
          </div>

          <!-- 密码：钥匙图标 + 可见切换与输入框同框（同用户名，flex 容器承载边框与光圈） -->
          <div class="flex items-center rounded-lg border border-slate-200 bg-white transition-all focus-within:border-blue-600 focus-within:ring-2 focus-within:ring-blue-500/20">
            <n-icon :component="KeyOutline" size="18" class="ml-4 shrink-0 text-slate-400" />
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="密码"
              autocomplete="current-password"
              class="w-full min-w-0 flex-1 rounded-lg bg-transparent py-4 pl-3 pr-2 text-sm text-slate-800 outline-none placeholder:text-slate-400"
              @keydown.enter="handleSubmit"
            />
            <button
              type="button"
              class="mr-3 shrink-0 text-slate-400 transition-colors hover:text-blue-600"
              :title="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <n-icon :component="showPassword ? EyeOffOutline : EyeOutline" size="18" />
            </button>
          </div>

          <!-- 确认密码（仅注册模式） -->
          <div
            v-if="mode === 'register'"
            class="flex items-center rounded-lg border border-slate-200 bg-white transition-all focus-within:border-blue-600 focus-within:ring-2 focus-within:ring-blue-500/20"
          >
            <n-icon :component="KeyOutline" size="18" class="ml-4 shrink-0 text-slate-400" />
            <input
              v-model="confirmPassword"
              type="password"
              placeholder="确认密码"
              autocomplete="new-password"
              class="w-full min-w-0 flex-1 rounded-lg bg-transparent py-4 pl-3 pr-4 text-sm text-slate-800 outline-none placeholder:text-slate-400"
              @keydown.enter="handleSubmit"
            />
          </div>

          <!-- 记住密码（仅登录模式） -->
          <label v-if="mode === 'login'" class="flex cursor-pointer select-none items-center gap-2">
            <input v-model="rememberMe" type="checkbox" class="h-4 w-4 rounded accent-brand-600" />
            <span class="text-sm text-slate-600">记住密码</span>
          </label>

          <!-- 登录/注册按钮-->
          <button
            type="submit"
            :disabled="loading"
            class="w-full rounded-lg bg-brand-500 py-3.5 font-medium text-white shadow-sm transition-all hover:bg-brand-700 active:bg-brand-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {{ loading ? (mode === 'login' ? '登录中…' : '注册中…') : mode === 'login' ? '登 录' : '注 册' }}
          </button>
        </form>

        <!-- 登录/注册切换 -->
        <p class="mt-10 text-center text-sm">
          <span class="text-slate-500">{{ mode === 'login' ? '还没有账号？' : '已有账号？' }}</span>
          <a
            class="cursor-pointer font-semibold text-brand-500 hover:underline"
            @click="switchMode"
          >{{ mode === 'login' ? '立即注册' : '返回登录' }}</a>
        </p>
      </div>

      <!-- 测试账号提示（仅登录模式）：测试阶段预置账号，方便演示与测试 -->
      <p v-if="mode === 'login'" class="mt-4 text-center text-[13px] text-slate-500">
        测试账号：root / 123456、user1 / 123456、user2 / 123456
      </p>
    </div>

    <!-- 法律协议弹窗（保留原交互：勾选后才可登录） -->
    <n-modal v-model:show="agreementShow" preset="card" style="width: 480px" title="欢迎使用法信通">
      <p class="text-[13px] leading-relaxed text-ink">
        在使用本平台前，请阅读并同意
        <a class="cursor-pointer text-brand-500 hover:underline" @click="openLegalDoc('user')">《用户协议》</a>、
        <a class="cursor-pointer text-brand-500 hover:underline" @click="openLegalDoc('privacy')">《隐私政策》</a>
        及
        <a class="cursor-pointer text-brand-500 hover:underline" @click="openLegalDoc('ai')">《AI 咨询非正式法律意见》声明</a>。
      </p>
      <div class="mt-4">
        <n-checkbox v-model:checked="agreementChecked">
          <span class="text-[13px]">我已阅读并同意上述协议与声明</span>
        </n-checkbox>
      </div>
      <template #footer>
        <div class="flex justify-end">
          <n-button
            type="primary"
            :disabled="!agreementChecked"
            @click="performLogin"
          >
            同意并继续
          </n-button>
        </div>
      </template>
    </n-modal>

    <!-- 协议文档查看弹窗 -->
    <n-modal v-model:show="docShow" preset="card" style="width: 440px" :title="docTitle">
      <pre class="whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{{ docBody }}</pre>
      <template #footer>
        <div class="flex justify-end">
          <n-button @click="docShow = false">知道了</n-button>
        </div>
      </template>
    </n-modal>
  </div>
</template>
