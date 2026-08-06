import { defineStore } from 'pinia'

/** 与旧版一致：trust=可信评估 / articles=法条溯源 / verification=引用核验 */
export type DetailTab = 'trust' | 'articles' | 'verification'

/**
 * 详情面板状态（不持久化）。
 * 核心思路：不复制数据——只记 selectedMsgId，面板内容直接读
 * sessions store 里对应消息的 meta（WS 推送更新 meta 时，响应式自动刷新面板）。
 */
export const useDetailPanelStore = defineStore('detailPanel', {
  state: () => ({
    selectedMsgId: null as string | null,
    activeTab: 'trust' as DetailTab,
    /** 面板开合。默认 true：打开页面即显示详情（不提问时显示空态），收起后提问会自动重新打开 */
    isOpen: true,
  }),

  actions: {
    /**
     * 点击 AI 消息：选中并展示详情（不再 toggle）。
     * 旧行为「再点同一消息取消选中」会让面板内容消失，且窄屏抽屉反复弹出遮罩，
     * 关闭面板统一用头部「收起」按钮。
     */
    selectMessage(msgId: string) {
      this.selectedMsgId = msgId
      this.isOpen = true
    },

    /**
     * 新回答完成后自动展示：不 toggle，直接选中并打开面板。
     * 追问时自动切到最新回答（详情面板数据源是消息对象本身，WS 核验更新自动刷新）。
     */
    autoShow(msgId: string) {
      this.selectedMsgId = msgId
      this.isOpen = true
      this.activeTab = 'trust'
    },

    setTab(tab: DetailTab) {
      this.activeTab = tab
    },

    /** 维度审计里的「查看引用核验 →」跳转 */
    jumpTo(tab: DetailTab) {
      this.activeTab = tab
      this.isOpen = true
    },

    close() {
      this.isOpen = false
      this.selectedMsgId = null
    },
  },
})
