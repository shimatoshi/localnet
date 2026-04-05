import { useState } from 'react'
import SubHeader from '../components/SubHeader'
import LogArea from '../components/LogArea'
import { useOnline } from '../hooks/useOnline'
import { useCrawl } from '../hooks/useCrawl'

export default function CrawlScreen() {
  const online = useOnline()
  const {
    sites, crawling, showLog, logs,
    doCrawl, doResume, doRecrawl, doBuild, stopCrawl, doDelete,
  } = useCrawl(online)

  const [crawlUrl, setCrawlUrl] = useState('')
  const [targetUrl, setTargetUrl] = useState('')
  const [depth, setDepth] = useState(0)
  const [delay, setDelay] = useState(1.0)
  const [exclude, setExclude] = useState('')
  const [showConfig, setShowConfig] = useState(false)

  function selectTarget() {
    let url = crawlUrl.trim()
    if (!url) return
    if (!url.startsWith('http')) url = 'https://' + url
    setCrawlUrl(url)
    setTargetUrl(url)
    setShowConfig(true)
  }

  if (!online) {
    return (
      <div className="screen">
        <SubHeader title="Crawl" />
        <p className="muted" style={{ padding: '40px 16px', textAlign: 'center' }}>サーバーに接続してください</p>
      </div>
    )
  }

  return (
    <div className="screen">
      <SubHeader title="Crawl" />

      <section>
        <div className="input-row">
          <input
            type="text"
            value={crawlUrl}
            onChange={(e) => setCrawlUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') selectTarget() }}
            placeholder="URL"
            autoComplete="url"
          />
          <button onClick={selectTarget}>設定</button>
        </div>
      </section>

      {crawling && (
        <section>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <span style={{ flex: 1 }}>クロール実行中...</span>
            <button className="btn-action" onClick={stopCrawl} style={{ background: 'var(--warn)', color: 'var(--bg)' }}>停止</button>
          </div>
        </section>
      )}

      {showConfig && (
        <section>
          <h2>{targetUrl}</h2>
          <div className="options-row">
            <label>
              深さ: <input type="number" value={depth} onChange={(e) => setDepth(parseInt(e.target.value) || 0)} min={0} max={999} placeholder="0=無制限" />
            </label>
            <label>
              遅延: <input type="number" value={delay} onChange={(e) => setDelay(parseFloat(e.target.value) || 1.0)} min={0.5} max={30} step={0.5} />s
            </label>
          </div>
          <div className="options-row">
            <label>
              除外: <input type="text" value={exclude} onChange={(e) => setExclude(e.target.value)} placeholder="パターン (カンマ区切り)" className="wide-input" />
            </label>
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
            <button className="btn-action" onClick={() => doCrawl(targetUrl, depth, delay, exclude)} disabled={crawling}>開始</button>
          </div>
        </section>
      )}

      <section style={{ marginTop: 12 }}>
        <h2>クロール済みサイト</h2>
        <div id="sites-list">
          {sites.length === 0 ? (
            <p className="muted">なし</p>
          ) : (
            sites.map((site) => (
              <div key={site.domain} className="site-item">
                <div className="site-domain">{site.domain}</div>
                <div className="site-stats">{site.file_count} ファイル</div>
                <div className="site-actions">
                  <button className="btn-resume" onClick={() => doResume(site.domain)}>再開</button>
                  {site.has_catalog ? (
                    <>
                      <button className="btn-downloaded" disabled>&#10003; {site.page_count} ページ</button>
                      <button className="btn-build" onClick={() => doBuild(site.domain)}>再生成</button>
                    </>
                  ) : (
                    <button className="btn-build" onClick={() => doBuild(site.domain)}>カタログ生成</button>
                  )}
                  <button className="btn-recrawl" onClick={() => doRecrawl(site.domain)}>再クロール</button>
                  <button className="btn-delete" onClick={() => doDelete(site.domain)}>削除</button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {showLog && (
        <section>
          <h2>ログ</h2>
          <LogArea logs={logs} />
        </section>
      )}
    </div>
  )
}
