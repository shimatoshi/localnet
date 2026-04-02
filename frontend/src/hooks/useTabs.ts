import { useState, useCallback, useRef } from 'react'

export interface Tab {
  id: number
  title: string
  url: string
  historyStack: { url: string; title: string }[]
  historyPos: number
}

let _idCounter = 0

function newTab(): Tab {
  return {
    id: ++_idCounter,
    title: '新しいタブ',
    url: '',
    historyStack: [],
    historyPos: -1,
  }
}

export function useTabs() {
  const [tabs, setTabs] = useState<Tab[]>(() => [newTab()])
  const [activeIndex, setActiveIndex] = useState(0)
  // refで最新のactiveIndexを保持（クロージャ問題を回避）
  const activeRef = useRef(activeIndex)
  activeRef.current = activeIndex

  const currentTab = tabs[activeIndex] ?? tabs[0]

  const addTab = useCallback(() => {
    setTabs((prev) => [...prev, newTab()])
    setActiveIndex((prev) => prev + 1)
  }, [])

  const closeTab = useCallback((index: number) => {
    setTabs((prev) => {
      const next = prev.filter((_, i) => i !== index)
      if (next.length === 0) return [newTab()]
      return next
    })
    setActiveIndex((prev) => {
      if (index < prev) return prev - 1
      if (index === prev) return Math.max(0, prev - 1)
      return prev
    })
  }, [])

  const switchTab = useCallback((index: number) => {
    setActiveIndex(index)
  }, [])

  const navigateTo = useCallback((url: string, title: string) => {
    setTabs((prev) => prev.map((tab, i) => {
      if (i !== activeRef.current) return tab
      const stack = tab.historyStack.slice(0, tab.historyPos + 1)
      stack.push({ url, title })
      return { ...tab, url, title: title || url, historyStack: stack, historyPos: stack.length - 1 }
    }))
  }, [])

  // 戻る/進むで移動先のURLを返す（BrowserScreenがloadPageに使う）
  const goBack = useCallback((): string | null => {
    let targetUrl: string | null = null
    setTabs((prev) => prev.map((tab, i) => {
      if (i !== activeRef.current || tab.historyPos <= 0) return tab
      const pos = tab.historyPos - 1
      const entry = tab.historyStack[pos]
      targetUrl = entry.url
      return { ...tab, url: entry.url, title: entry.title, historyPos: pos }
    }))
    return targetUrl
  }, [])

  const goForward = useCallback((): string | null => {
    let targetUrl: string | null = null
    setTabs((prev) => prev.map((tab, i) => {
      if (i !== activeRef.current || tab.historyPos >= tab.historyStack.length - 1) return tab
      const pos = tab.historyPos + 1
      const entry = tab.historyStack[pos]
      targetUrl = entry.url
      return { ...tab, url: entry.url, title: entry.title, historyPos: pos }
    }))
    return targetUrl
  }, [])

  const updateCurrentTab = useCallback((updates: Partial<Tab>) => {
    setTabs((prev) => prev.map((tab, i) => {
      if (i !== activeRef.current) return tab
      return { ...tab, ...updates }
    }))
  }, [])

  return {
    tabs,
    activeIndex,
    currentTab,
    addTab,
    closeTab,
    switchTab,
    navigateTo,
    goBack,
    goForward,
    updateCurrentTab,
    canGoBack: currentTab.historyPos > 0,
    canGoForward: currentTab.historyPos < currentTab.historyStack.length - 1,
  }
}
