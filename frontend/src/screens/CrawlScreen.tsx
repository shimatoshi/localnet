import { useState, useEffect, useRef } from 'react'
import SubHeader from '../components/SubHeader'
import LogArea from '../components/LogArea'
import { useOnline } from '../hooks/useOnline'
import { useSSE } from '../hooks/useSSE'
import {
  apiGetSites, apiCrawl, apiResume, apiRecrawl, apiBuild,
  apiStopJob, apiExport, apiImport, apiGetActiveJobs,
  type SiteInfo, type JobInfo,
} from '../api/client'

export default function CrawlScreen() {
  const online = useOnline()
  const { logs, addLog, clearLogs, listen } = useSSE()
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [crawlUrl, setCrawlUrl] = useState('')
  const [targetUrl, setTargetUrl] = useState('')
  const [depth, setDepth] = useState(0)
  const [delay, setDelay] = useState(1.0)
  const [exclude, setExclude] = useState('')
  const [crawling, setCrawling] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const [showLog, setShowLog] = useState(false)
  const currentJobIdRef = useRef<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const importRef = useRef<HTMLInputElement>(null)
  const [importStatus, setImportStatus] = useState('')

  useEffect(() => {
    if (online) {
      loadSites()
      checkActiveJobs()
    }
    return () => clearInterval(pollRef.current)
  }, [online])

  async function loadSites() {
    try {
      setSites(await apiGetSites())
    } catch { /* ignore */ }
  }

  async function checkActiveJobs() {
    if (currentJobIdRef.current) return
    try {
      const jobs = await apiGetActiveJobs()
      if (jobs.length > 0) {
        const job = jobs[0]
        currentJobIdRef.current = job.job_id
        setCrawling(true)
        setShowLog(true)
        addLog(`実行中のジョブに再接続: ${job.job_id} (${job.domain || ''})`)
        addLog(`現在: ${job.page_count || 0} 件取得済み`)
        listen(job.job_id, onJobFinish)
      }
    } catch { /* ignore */ }
  }

  function onJobFinish() {
    setCrawling(false)
    currentJobIdRef.current = null
    clearInterval(pollRef.current)
    loadSites()
  }

  function startListening(job: JobInfo) {
    currentJobIdRef.current = job.job_id
    setCrawling(true)
    setShowLog(true)
    listen(job.job_id, onJobFinish)
  }

  function selectTarget() {
    let url = crawlUrl.trim()
    if (!url) return
    if (!url.startsWith('http')) url = 'https://' + url
    setCrawlUrl(url)
    setTargetUrl(url)
    setShowConfig(true)
  }

  async function doCrawl() {
    if (!targetUrl) return
    const excludeList = exclude ? exclude.split(',').map((s) => s.trim()).filter(Boolean) : []
    clearLogs()
    try {
      const data = await apiCrawl(targetUrl, depth, delay, excludeList)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`クロール開始: ${data.job_id} (深さ: ${depth === 0 ? '無制限' : depth})`)
      startListening(data)
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doResume(domain: string) {
    clearLogs()
    try {
      const data = await apiResume(domain)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`再開: ${data.job_id} (${domain})`)
      startListening(data)
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doRecrawl(domain: string) {
    if (!confirm(`${domain} を再クロールしますか？\n既存のキャッシュは上書きされます。`)) return
    clearLogs()
    try {
      const data = await apiRecrawl(domain)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`再クロール開始: ${data.job_id} (${domain})`)
      startListening(data)
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doBuild(domain: string) {
    clearLogs()
    setShowLog(true)
    try {
      const data = await apiBuild(domain)
      if (data.error) { addLog('エラー: ' + data.error); return }
      addLog(`カタログ生成: ${data.job_id}`)
      listen(data.job_id, () => loadSites())
    } catch (e) {
      addLog('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function stopCrawl() {
    if (!currentJobIdRef.current) return
    try {
      const data = await apiStopJob(currentJobIdRef.current)
      if (data.ok) addLog('停止リクエスト送信...')
      else addLog('停止失敗: ' + (data.error || '不明なエラー'))
    } catch (e) {
      addLog('停止エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function doExport(domain: string) {
    try {
      const blob = await apiExport(domain)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${domain}.tar.gz`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      alert('エクスポートエラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function handleImport(file: File) {
    setImportStatus(`アップロード中: ${file.name}...`)
    try {
      const data = await apiImport(file)
      setImportStatus(`カタログ生成中: ${data.domain || '...'} (job: ${data.job_id})`)
      listen(data.job_id, () => {
        setImportStatus('インポート完了')
        loadSites()
      })
    } catch (e) {
      setImportStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
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
            <button className="btn-action" onClick={doCrawl} disabled={crawling}>開始</button>
            {crawling && (
              <button className="btn-action" onClick={stopCrawl} style={{ background: 'var(--warn)', color: 'var(--bg)' }}>停止</button>
            )}
          </div>
        </section>
      )}

      <section style={{ marginTop: 12 }}>
        <h2>サイト</h2>
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
                  <button className="btn-export" onClick={() => doExport(site.domain)}>エクスポート</button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      <section style={{ marginTop: 12 }}>
        <h2>インポート</h2>
        <p className="muted" style={{ margin: '0 0 8px' }}>tar.gz アーカイブからサーバー経由で復元</p>
        <label className="btn-import-label">
          .tar.gz を選択
          <input
            ref={importRef}
            type="file"
            accept=".tar.gz,.tgz,.tar"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleImport(file)
              e.target.value = ''
            }}
          />
        </label>
        {importStatus && <div style={{ marginTop: 8 }}><p className="muted">{importStatus}</p></div>}
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
