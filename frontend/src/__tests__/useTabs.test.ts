import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useTabs } from '../hooks/useTabs'

describe('useTabs', () => {
  // _idCounter is module-level so we just work with what we get

  it('starts with one empty tab', () => {
    const { result } = renderHook(() => useTabs())
    expect(result.current.tabs).toHaveLength(1)
    expect(result.current.activeIndex).toBe(0)
    expect(result.current.currentTab.url).toBe('')
    expect(result.current.currentTab.title).toBe('新しいタブ')
  })

  it('addTab creates a new tab and switches to it', () => {
    const { result } = renderHook(() => useTabs())
    act(() => {
      result.current.addTab()
    })
    expect(result.current.tabs).toHaveLength(2)
    expect(result.current.activeIndex).toBe(1)
  })

  it('navigateTo updates the current tab URL and builds history', () => {
    const { result } = renderHook(() => useTabs())
    act(() => {
      result.current.navigateTo('https://example.com', 'Example')
    })
    expect(result.current.currentTab.url).toBe('https://example.com')
    expect(result.current.currentTab.title).toBe('Example')
    expect(result.current.currentTab.historyStack).toHaveLength(1)
    expect(result.current.currentTab.historyPos).toBe(0)
  })

  it('goBack returns the previous URL', () => {
    const { result } = renderHook(() => useTabs())
    act(() => {
      result.current.navigateTo('https://a.com', 'A')
    })
    act(() => {
      result.current.navigateTo('https://b.com', 'B')
    })
    expect(result.current.currentTab.historyStack).toHaveLength(2)
    expect(result.current.canGoBack).toBe(true)

    act(() => {
      result.current.goBack()
    })
    // After goBack, the tab should reflect the previous URL
    expect(result.current.currentTab.url).toBe('https://a.com')
    expect(result.current.currentTab.historyPos).toBe(0)
    expect(result.current.canGoBack).toBe(false)
  })

  it('goBack returns null when there is no history', () => {
    const { result } = renderHook(() => useTabs())
    let url: string | null = 'initial'
    act(() => {
      url = result.current.goBack()
    })
    expect(url).toBeNull()
  })

  it('goForward returns the next URL', () => {
    const { result } = renderHook(() => useTabs())
    act(() => {
      result.current.navigateTo('https://a.com', 'A')
    })
    act(() => {
      result.current.navigateTo('https://b.com', 'B')
    })
    act(() => {
      result.current.goBack()
    })
    expect(result.current.canGoForward).toBe(true)

    act(() => {
      result.current.goForward()
    })
    // After goForward, the tab should reflect the next URL
    expect(result.current.currentTab.url).toBe('https://b.com')
    expect(result.current.canGoForward).toBe(false)
  })

  it('goForward returns null when at the end of history', () => {
    const { result } = renderHook(() => useTabs())
    act(() => {
      result.current.navigateTo('https://a.com', 'A')
    })
    let url: string | null = 'initial'
    act(() => {
      url = result.current.goForward()
    })
    expect(url).toBeNull()
  })

  it('navigateTo after goBack truncates forward history', () => {
    const { result } = renderHook(() => useTabs())
    act(() => { result.current.navigateTo('https://a.com', 'A') })
    act(() => { result.current.navigateTo('https://b.com', 'B') })
    act(() => { result.current.navigateTo('https://c.com', 'C') })
    act(() => { result.current.goBack() })
    act(() => { result.current.goBack() })
    // Now at A, forward history had B and C
    act(() => { result.current.navigateTo('https://d.com', 'D') })
    expect(result.current.currentTab.historyStack).toHaveLength(2)
    expect(result.current.currentTab.historyStack[0].url).toBe('https://a.com')
    expect(result.current.currentTab.historyStack[1].url).toBe('https://d.com')
    expect(result.current.canGoForward).toBe(false)
  })

  it('closeTab removes the tab and adjusts activeIndex', () => {
    const { result } = renderHook(() => useTabs())
    act(() => { result.current.addTab() })
    act(() => { result.current.addTab() })
    expect(result.current.tabs).toHaveLength(3)
    expect(result.current.activeIndex).toBe(2)

    // Close the middle tab (index 1)
    act(() => { result.current.closeTab(1) })
    expect(result.current.tabs).toHaveLength(2)
    // Active was 2, closing 1 (before active) shifts it down
    expect(result.current.activeIndex).toBe(1)
  })

  it('closeTab on last remaining tab creates a fresh tab', () => {
    const { result } = renderHook(() => useTabs())
    act(() => { result.current.navigateTo('https://a.com', 'A') })
    act(() => { result.current.closeTab(0) })
    expect(result.current.tabs).toHaveLength(1)
    expect(result.current.currentTab.url).toBe('')
    expect(result.current.currentTab.title).toBe('新しいタブ')
  })

  it('switchTab changes the active index', () => {
    const { result } = renderHook(() => useTabs())
    act(() => { result.current.addTab() })
    act(() => { result.current.addTab() })
    act(() => { result.current.switchTab(0) })
    expect(result.current.activeIndex).toBe(0)
  })

  it('updateCurrentTab merges partial updates', () => {
    const { result } = renderHook(() => useTabs())
    act(() => { result.current.updateCurrentTab({ title: 'Updated' }) })
    expect(result.current.currentTab.title).toBe('Updated')
  })
})
