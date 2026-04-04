/**
 * BrowserScreen 戻るボタン統合テスト
 *
 * 検索結果→ブラウザ→iframe内リンク→戻る のフローを
 * React Router + useTabs で再現し、履歴が正しく動くか確認する
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom'
import BrowserScreen from '../screens/BrowserScreen'

// API・ストアをモック
vi.mock('../api/client', () => ({
  apiGetCachePage: vi.fn(() =>
    Promise.resolve({
      ok: true,
      headers: new Headers({ 'Content-Type': 'text/html; charset=utf-8' }),
      arrayBuffer: () =>
        Promise.resolve(new TextEncoder().encode('<html><head><title>Test</title></head><body>hello</body></html>').buffer),
    }),
  ),
}))

vi.mock('../stores/db', () => ({
  historyStore: { add: vi.fn(() => Promise.resolve()) },
  bookmarkStore: { has: vi.fn(() => Promise.resolve(false)) },
}))

// 現在のlocationを表示するヘルパーコンポーネント
function LocationDisplay() {
  const loc = useLocation()
  return <div data-testid="location">{loc.pathname}{loc.search}</div>
}

// 検索結果画面のモック（リンクをクリックすると/browserに遷移）
function MockSearchScreen() {
  const navigate = useNavigate()
  return (
    <div>
      <div data-testid="search-screen">検索結果</div>
      <button onClick={() => navigate('/browser?url=https%3A%2F%2Fexample.com%2Fpage1')}>
        Open Page1
      </button>
    </div>
  )
}

function renderWithRouter(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/search" element={<MockSearchScreen />} />
        <Route path="/browser" element={<BrowserScreen />} />
      </Routes>
      <LocationDisplay />
    </MemoryRouter>,
  )
}

describe('BrowserScreen 戻るボタン', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('検索画面→ブラウザ→戻るで検索画面に戻れ���', async () => {
    // 検索画面からスタート
    const { getByText, getByTestId } = renderWithRouter('/search?q=test')

    // 検索画面が表示されている
    expect(getByTestId('search-screen')).toBeTruthy()

    // ブラウザ画面に遷移
    await act(async () => {
      fireEvent.click(getByText('Open Page1'))
    })

    // ブラウザ画面に遷移したことを確認
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(getByTestId('location').textContent).toContain('/browser')

    // 戻るボタン（◀）をクリック
    const backBtn = screen.getAllByRole('button').find(b => b.textContent === '◀')
    expect(backBtn).toBeTruthy()

    await act(async () => {
      fireEvent.click(backBtn!)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })

    // 検索画面に戻れたことを確認
    const loc = getByTestId('location').textContent
    console.log('After back from single page:', loc)
    expect(loc).toContain('/search')
  })

  it('iframe内リンク遷移後、正しい回数の戻るで検索画面に戻れる', async () => {
    const { getByText, getByTestId } = renderWithRouter('/search?q=test')

    // ブラウザ画面に遷移
    await act(async () => {
      fireEvent.click(getByText('Open Page1'))
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    expect(getByTestId('location').textContent).toContain('/browser')
    expect(getByTestId('location').textContent).toContain('page1')

    // iframe内リンククリックをシミュレート（postMessage）
    // jsdomではpostMessageのoriginがwindow.location.originになる
    await act(async () => {
      const event = new MessageEvent('message', {
        data: { type: 'navigate', url: 'https://example.com/page2' },
        origin: window.location.origin,
      })
      window.dispatchEvent(event)
      await new Promise((r) => setTimeout(r, 200))
    })

    console.log('After iframe nav to page2:', getByTestId('location').textContent)

    // もう1つiframe内リンク
    await act(async () => {
      const event = new MessageEvent('message', {
        data: { type: 'navigate', url: 'https://example.com/page3' },
        origin: window.location.origin,
      })
      window.dispatchEvent(event)
      await new Promise((r) => setTimeout(r, 200))
    })

    console.log('After iframe nav to page3:', getByTestId('location').textContent)

    // 戻る1回目: page3 → page2
    const backBtn = () => screen.getAllByRole('button').find(b => b.textContent === '◀')

    await act(async () => {
      fireEvent.click(backBtn()!)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const loc1 = getByTestId('location').textContent!
    console.log('After back 1:', loc1)

    // 戻る2回目: page2 → page1
    await act(async () => {
      fireEvent.click(backBtn()!)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const loc2 = getByTestId('location').textContent!
    console.log('After back 2:', loc2)

    // 戻る3回目: page1 → 検索画面
    await act(async () => {
      fireEvent.click(backBtn()!)
    })
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100))
    })
    const loc3 = getByTestId('location').textContent!
    console.log('After back 3 (should be search):', loc3)
    expect(loc3).toContain('/search')
  })

  it('履歴が増殖しない（3ページ遷移なら戻る3回で検索に戻る）', async () => {
    const { getByText, getByTestId } = renderWithRouter('/search?q=test')

    // ブラウザ画面に遷移
    await act(async () => {
      fireEvent.click(getByText('Open Page1'))
    })
    await act(async () => { await new Promise((r) => setTimeout(r, 100)) })

    // iframe内リンク2回
    await act(async () => {
      window.dispatchEvent(new MessageEvent('message', {
        data: { type: 'navigate', url: 'https://example.com/page2' },
        origin: window.location.origin,
      }))
      await new Promise((r) => setTimeout(r, 200))
    })
    await act(async () => {
      window.dispatchEvent(new MessageEvent('message', {
        data: { type: 'navigate', url: 'https://example.com/page3' },
        origin: window.location.origin,
      }))
      await new Promise((r) => setTimeout(r, 200))
    })

    // 戻るボタンを何回押したか数える
    const backBtn = () => screen.getAllByRole('button').find(b => b.textContent === '◀')
    let backCount = 0
    const maxPresses = 10  // 安全弁

    while (backCount < maxPresses) {
      const locBefore = getByTestId('location').textContent!
      if (locBefore.includes('/search')) break

      await act(async () => {
        fireEvent.click(backBtn()!)
      })
      await act(async () => { await new Promise((r) => setTimeout(r, 100)) })
      backCount++
    }

    const finalLoc = getByTestId('location').textContent!
    console.log(`Took ${backCount} back presses to reach: ${finalLoc}`)

    // page1, page2, page3 の3ページなので、戻る3回で検索画面に到達すべき
    expect(backCount).toBe(3)
    expect(finalLoc).toContain('/search')
  })
})
