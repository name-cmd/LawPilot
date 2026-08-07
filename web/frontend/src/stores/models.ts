import { defineStore } from 'pinia'
import { fetchModels } from '@/api/misc'
import type { ApiModelInfo, LocalEngineInfo } from '@/api/types'

/**
 * 模型目录 store：从后端 /api/models 拉取，模型选择器与设置面板共用。
 * 失败不阻塞聊天（error 提示 + 选择器回退占位），与后端解耦。
 */
export const useModelsStore = defineStore('models', {
  state: () => ({
    apiModels: [] as ApiModelInfo[],
    localEngine: null as LocalEngineInfo | null,
    defaultModel: '',
    loading: false,
    error: '',
  }),
  getters: {
    /** 启用中的模型（is_enabled 过滤，注册表驱动） */
    enabledModels(state): ApiModelInfo[] {
      return state.apiModels.filter((m) => m.is_enabled)
    },
    /** 后端标注的默认模型条目（is_default） */
    defaultModelInfo(state): ApiModelInfo | null {
      return state.apiModels.find((m) => m.is_default) ?? null
    },
  },
  actions: {
    async fetchModels() {
      this.loading = true
      this.error = ''
      try {
        const data = await fetchModels()
        this.apiModels = data.api_models
        this.localEngine = data.local_engine
        this.defaultModel = data.default_model
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e)
      } finally {
        this.loading = false
      }
    },
  },
})
