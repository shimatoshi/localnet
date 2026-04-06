import { useState } from 'react'
import SubHeader from '../components/SubHeader'
import { useCrawl } from '../hooks/useCrawl'
import { getRemoteServer, setRemoteServer, apiGetRemoteSites, apiPullSite, type SiteInfo } from '../api/client'

export default function CrawlScreen() {
  const {
    crawling, statusMsg,
    doCrawl, stopCrawl, checkStatus,
  } = useCrawl(true)

  const [serverUrl, setServerUrl] = useState(getRemoteServer())
  const [serverSaved, setServerSaved] = useState(!!getRemoteServer())
  const [crawlUrl, setCrawlUrl] = useState('')
  const [depth, setDepth] = useState(0)
  const [delay, setDelay] = useState(1.0)
  const [exclude, setExclude] = useState('')
  const [showConfig, setShowConfig] = useState(false)

  // リモート成果物
  const [remoteSites, setRemoteSites] = useState<SiteInfo[]>([])
  const [pulling, setPulling] = useState<Record<string, string>>({})

  function saveServer() {
    setRemoteServer(serverUrl)
    setServerSaved(!!serverUrl.trim())
  }

  async function loadRemoteSites() {
    try {
      setRemoteSites(await apiGetRemoteSites())
    } catch (e) {
      setPulling(prev => ({ ...prev, _error: '取得エラー: ' + (e instanceof Error ? e.message : String(e)) }))
    }
  }

  async function pullSite(domain: string) {
    setPulling(prev => ({ ...prev, [domain]: '取り込み中...' }))
    try {
      await apiPullSite(domain)
      setPulling(prev => ({ ...prev, [domain]: '完了' }))
    } catch (e) {
      setPulling(prev => ({ ...prev, [domain]: 'エラー: ' + (e instanceof Error ? e.message : String(e)) }))
    }
  }

  function selectTarget() {
    let url = crawlUrl.trim()
    if (!url) return
    if (!url.startsWith('http')) url = 'https://' + url
    setCrawlUrl(url)
    setShowConfig(true)
  }

  function startCrawl() {
    doCrawl(crawlUrl, depth, delay, exclude)
    setShowConfig(false)
  }

  return (
    <div className="screen">
      <SubHeader title="Crawl" />

      {/* サーバー設定 */}
      <section>
        <h2>サーバー</h2>
        <div className="input-row">
          <input
            type="text"
            value={serverUrl}
            onChange={(e) => setServerUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') saveServer() }}
            placeholder="http://100.74.138.17:8789"
          />
          <button onClick={saveServer}>保存</button>
        </div>
        {serverSaved && <p className="muted" style={{ margin: '4px 0 0', fontSize: '0.85em' }}>接続先: {getRemoteServer()}</p>}
      </section>

      {/* クロール開始 */}
      {serverSaved && (
        <>
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

          {showConfig && (
            <section>
              <h2>{crawlUrl}</h2>
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
                <button className="btn-action" onClick={startCrawl} disabled={crawling}>開始</button>
              </div>
            </section>
          )}

          {/* ジョブ状況 */}
          <section>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <button onClick={checkStatus}>状況を確認</button>
              {crawling && (
                <button onClick={stopCrawl} style={{ background: 'var(--warn)', color: 'var(--bg)' }}>停止</button>
              )}
            </div>
            {statusMsg && (
              <p style={{ margin: '8px 0 0', fontSize: '0.9em' }}>{statusMsg}</p>
            )}
          </section>

          {/* サーバーから取り込み */}
          <section>
            <h2>サーバーから取り込み</h2>
            <button onClick={loadRemoteSites}>サイト一覧を取得</button>
            {pulling._error && <p style={{ margin: '8px 0 0', fontSize: '0.9em', color: 'var(--warn)' }}>{pulling._error}</p>}
            {remoteSites.length > 0 && (
              <div id="sites-list" style={{ marginTop: 8 }}>
                {remoteSites.map((site) => (
                  <div key={site.domain} className="site-item">
                    <div className="site-domain">{site.domain}</div>
                    <div className="site-stats">{site.page_count} ページ / {site.file_count} ファイル</div>
                    <div className="site-actions">
                      <button
                        className="btn-action"
                        disabled={!!pulling[site.domain]}
                        onClick={() => pullSite(site.domain)}
                      >
                        {pulling[site.domain] || '取り込み'}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  )
}
