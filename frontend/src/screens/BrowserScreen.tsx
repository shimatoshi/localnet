import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { apiGetCachePage } from '../api/client'
import { historyStore, bookmarkStore } from '../stores/db'
import { useTabs } from '../hooks/useTabs'

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

export default function BrowserScreen() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const urlParam = params.get('url') || ''
  const frameRef = useRef<HTMLIFrameElement>(null)
  const [menuOpen, setMenuOpen] = useState(false)
  const [isBookmarked, setIsBookmarked] = useState(false)

  // 内部ナビゲーション中はuseEffectの urlParam 変更検知を抑制するフラグ
  const internalNav = useRef(false)

  const {
    currentTab, navigateTo, goBack, goForward,
    canGoBack, canGoForward, updateCurrentTab, tabs,
  } = useTabs()

  const loadPage = useCallback(async (url: string, addToHistory: boolean) => {
    const frame = frameRef.current
    if (!frame) return

    frame.srcdoc = '<p style="color:#888;padding:20px;font-family:sans-serif">読み込み中...</p>'

    let parsed: URL
    try {
      parsed = new URL(url)
    } catch {
      frame.srcdoc = '<p style="color:#888;padding:20px;font-family:sans-serif">不正なURLです</p>'
      return
    }

    const domain = parsed.hostname
    const path = parsed.pathname.replace(/^\//, '')

    try {
      const res = await apiGetCachePage(domain, path)
      if (!res.ok) {
        frame.srcdoc = `<div style="color:#888;padding:20px;font-family:sans-serif">
          <p>このページはローカルにありません</p>
          <p style="font-size:0.85em;margin-top:8px;word-break:break-all">${escHtml(url)}</p>
        </div>`
        return
      }

      const ct = res.headers.get('Content-Type') || ''
      const charsetMatch = ct.match(/charset=([a-zA-Z0-9_-]+)/i)
      const charset = charsetMatch ? charsetMatch[1] : 'utf-8'
      const buf = await res.arrayBuffer()
      let html = new TextDecoder(charset, { fatal: false }).decode(buf)

      // タイトル抽出
      const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i)
      const title = titleMatch ? titleMatch[1].replace(/<[^>]+>/g, '').trim() : url

      // 絶対パス書き換え
      const cachePrefix = `/api/cache/${domain}`
      html = html.replace(
        /((?:src|href|action)\s*=\s*["'])\/(?!\/)/gi,
        `$1${cachePrefix}/`,
      )

      // <base>タグ
      const baseDir = path.replace(/[^/]*$/, '')
      const baseTag = `<base href="${cachePrefix}/${baseDir}">`
      if (/<head/i.test(html)) {
        html = html.replace(/<head([^>]*)>/i, `<head$1>${baseTag}`)
      } else {
        html = baseTag + html
      }

      // リンクインターセプト
      const interceptScript = `
        <script>
          document.addEventListener('click', function(e) {
            var a = e.target.closest('a');
            if (!a) return;
            e.preventDefault();
            e.stopPropagation();
            var href = a.href;
            if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
            var m = href.match(/\\/api\\/cache\\/([^\\/]+)\\/(.*)/);
            if (m) {
              window.parent.postMessage({ type: 'navigate', url: 'https://' + m[1] + '/' + m[2] }, '*');
            } else if (href.startsWith('http')) {
              window.parent.postMessage({ type: 'navigate', url: href }, '*');
            }
          }, true);
        </script>
      `
      if (html.includes('</body>')) {
        html = html.replace('</body>', interceptScript + '</body>')
      } else {
        html += interceptScript
      }

      frame.srcdoc = html

      updateCurrentTab({ title, url })

      if (addToHistory) {
        historyStore.add({ url, title })
      }

      const bm = await bookmarkStore.has(url)
      setIsBookmarked(bm)
    } catch (e) {
      frame.srcdoc = `<p style="color:#888;padding:20px;font-family:sans-serif">エラー: ${escHtml(e instanceof Error ? e.message : String(e))}</p>`
    }
  }, [updateCurrentTab])

  // 外部からの遷移（検索画面→ブラウザ等）のみ処理。
  // iframe内リンク・戻る・進むは internalNav フラグで抑制。
  useEffect(() => {
    if (internalNav.current) {
      internalNav.current = false
      return
    }
    if (urlParam && urlParam !== currentTab.url) {
      navigateTo(urlParam, '')
      loadPage(urlParam, true)
    }
  }, [urlParam]) // eslint-disable-line react-hooks/exhaustive-deps

  // iframe内ナビゲーション: useTabs に直接追加、useEffectを経由しない
  useEffect(() => {
    function handleMessage(e: MessageEvent) {
      if (e.origin !== window.location.origin && e.origin !== 'null') return
      if (e.data?.type === 'navigate') {
        const url = e.data.url
        internalNav.current = true
        navigateTo(url, '')
        loadPage(url, true)
        // URLバーだけ同期（React Router履歴は増やさない）
        navigate(`/browser?url=${encodeURIComponent(url)}`, { replace: true })
      }
    }
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [navigate, navigateTo, loadPage])

  async function toggleBookmark() {
    setMenuOpen(false)
    if (!currentTab.url) return
    if (isBookmarked) {
      await bookmarkStore.remove(currentTab.url)
    } else {
      await bookmarkStore.add({ url: currentTab.url, title: currentTab.title })
    }
    setIsBookmarked(!isBookmarked)
  }

  function sharePage() {
    setMenuOpen(false)
    if (!currentTab.url) return
    if (navigator.share) {
      navigator.share({ title: currentTab.title, url: currentTab.url }).catch(() => {})
    } else {
      navigator.clipboard.writeText(currentTab.url).then(() => alert('URLをコピーしました'))
    }
  }

  function handleBack() {
    const url = goBack()
    if (url) {
      internalNav.current = true
      navigate(`/browser?url=${encodeURIComponent(url)}`, { replace: true })
      loadPage(url, false)
    } else {
      // タブ内履歴がなければReact Routerの履歴を戻る（検索結果等に戻る）
      navigate(-1)
    }
  }

  function handleForward() {
    const url = goForward()
    if (url) {
      internalNav.current = true
      navigate(`/browser?url=${encodeURIComponent(url)}`, { replace: true })
      loadPage(url, false)
    }
  }

  return (
    <div className="screen" id="screen-browser" style={{ display: 'flex', flexDirection: 'column' }}>
      <iframe ref={frameRef} id="browser-frame" title="ページビューア" sandbox="allow-scripts allow-same-origin" />
      <div id="browser-bar">
        <button className="bar-btn" onClick={handleBack}>&#9664;</button>
        <button className="bar-btn" disabled={!canGoForward} onClick={handleForward}>&#9654;</button>
        <button className="bar-btn" onClick={() => navigate('/')}>&#9679;</button>
        <button className="bar-btn" id="btn-tabs" onClick={() => navigate('/tabs')}>
          <span id="tab-count">{tabs.length}</span>
        </button>
        <button className="bar-btn" onClick={() => setMenuOpen(!menuOpen)}>&#8942;</button>
      </div>
      {menuOpen && (
        <div id="browser-menu">
          <button onClick={toggleBookmark}>
            <span>{isBookmarked ? '\u2605' : '\u2606'}</span> ブックマーク
          </button>
          <button onClick={sharePage}>&#8599; 共有</button>
          <button onClick={() => { setMenuOpen(false); navigate('/history') }}>&#9201; 履歴</button>
          <button onClick={() => { setMenuOpen(false); navigate('/bookmarks') }}>&#9733; ブックマーク一覧</button>
          <button onClick={() => { setMenuOpen(false); navigate('/crawl') }}>&#127760; クロール</button>
        </div>
      )}
    </div>
  )
}
