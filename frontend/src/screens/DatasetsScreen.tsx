import { useState, useEffect, useCallback } from 'react'
import SubHeader from '../components/SubHeader'
import EmptyState from '../components/EmptyState'
import SiteItem from '../components/SiteItem'
import DatasetItem from '../components/DatasetItem'
import { useOnline } from '../hooks/useOnline'
import {
  apiGetSites, apiListSharedDatasets, apiRefreshSharedDatasets,
  apiDownloadSharedDataset, apiBuild, apiDeleteSite,
  apiGetRemoteSites, apiPullSite, getRemoteServer,
  type SiteInfo, type SharedDataset,
} from '../api/client'

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DatasetsScreen() {
  const online = useOnline()
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [shared, setShared] = useState<SharedDataset[]>([])
  const [downloading, setDownloading] = useState<Record<string, string>>({})
  const [remoteSites, setRemoteSites] = useState<SiteInfo[]>([])
  const [pulling, setPulling] = useState<Record<string, string>>({})
  const [error, setError] = useState('')
  const [loadingShared, setLoadingShared] = useState(false)

  const loadSites = useCallback(async () => {
    try {
      setSites(await apiGetSites())
      setError('')
    } catch (e) {
      setError('サイト取得エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }, [])

  const loadShared = useCallback(async () => {
    try { setShared(await apiListSharedDatasets()) } catch { /* */ }
  }, [])

  const refreshShared = useCallback(async () => {
    setLoadingShared(true)
    try {
      await apiRefreshSharedDatasets()
      setShared(await apiListSharedDatasets())
    } catch { /* */ }
    setLoadingShared(false)
  }, [])

  useEffect(() => {
    loadSites()
    if (online) loadShared()
  }, [online, loadSites, loadShared])

  const localDomains = new Set(sites.map(s => s.domain))

  async function downloadShared(ds: SharedDataset) {
    setDownloading(prev => ({ ...prev, [ds.name]: 'ダウンロード中...' }))
    try {
      const r = await apiDownloadSharedDataset(ds.name, ds.download_url)
      if (r.error) {
        setDownloading(prev => ({ ...prev, [ds.name]: 'エラー: ' + r.error }))
        return
      }
      setDownloading(prev => ({ ...prev, [ds.name]: '完了' }))
      loadSites()
    } catch {
      setDownloading(prev => ({ ...prev, [ds.name]: 'エラー' }))
    }
  }

  async function doBuild(domain: string) {
    try { await apiBuild(domain); loadSites() } catch { /* */ }
  }

  async function doDelete(domain: string) {
    if (!confirm(`${domain} を削除しますか？`)) return
    try { await apiDeleteSite(domain); loadSites() } catch { /* */ }
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
      loadSites()
    } catch (e) {
      setPulling(prev => ({ ...prev, [domain]: 'エラー: ' + (e instanceof Error ? e.message : String(e)) }))
    }
  }

  return (
    <div className="screen">
      <SubHeader title="Data" />

      {/* データセット一覧 */}
      <section>
        <div className="flex-between">
          <h2 style={{ border: 'none', margin: 0, padding: 0 }}>データセット</h2>
          <button className="btn-small" onClick={loadSites}>更新</button>
        </div>
        {error && <p className="warn-msg">{error}</p>}
        {sites.length === 0 && !error ? (
          <EmptyState message="なし — Crawlタブからサイトを取り込めます" />
        ) : (
          sites.map((site) => (
            <SiteItem
              key={site.domain}
              site={site}
              actions={
                <>
                  {site.has_catalog ? (
                    <>
                      <button className="btn-downloaded" disabled>&#10003; {site.page_count} ページ</button>
                      <button className="btn-build" onClick={() => doBuild(site.domain)}>再生成</button>
                    </>
                  ) : (
                    <button className="btn-build" onClick={() => doBuild(site.domain)}>カタログ生成</button>
                  )}
                  <button className="btn-delete" onClick={() => doDelete(site.domain)}>削除</button>
                </>
              }
            />
          ))
        )}
      </section>

      {/* サーバーから取り込み */}
      {getRemoteServer() && (
        <section>
          <h2>サーバーから取り込み</h2>
          <button className="btn-action" onClick={loadRemoteSites}>サイト一覧を取得</button>
          {pulling._error && <p className="warn-msg">{pulling._error}</p>}
          {remoteSites.length > 0 && (
            <div id="sites-list" style={{ marginTop: 8 }}>
              {remoteSites.map((site) => (
                <SiteItem
                  key={site.domain}
                  site={site}
                  badge={localDomains.has(site.domain) ? <span className="muted" style={{ marginLeft: 8, fontSize: '0.85em' }}>DL済み</span> : undefined}
                  actions={
                    <button
                      className="btn-action"
                      disabled={!!pulling[site.domain]}
                      onClick={() => pullSite(site.domain)}
                    >
                      {pulling[site.domain] || (localDomains.has(site.domain) ? '更新' : '取り込み')}
                    </button>
                  }
                />
              ))}
            </div>
          )}
        </section>
      )}

      {/* 共有データセット */}
      {online && (
        <section>
          <div className="flex-between">
            <h2 style={{ border: 'none', margin: 0, padding: 0 }}>共有データセット</h2>
            <button className="btn-small" onClick={refreshShared} disabled={loadingShared}>
              {loadingShared ? '取得中...' : '更新'}
            </button>
          </div>
          {shared.length === 0 ? (
            <EmptyState message={loadingShared ? '取得中...' : '「更新」を押して最新の共有データセットを取得'} />
          ) : (
            shared.map((ds) => (
              <DatasetItem
                key={ds.name + ds.tag}
                name={ds.name}
                info={`${ds.description ? ds.description + ' / ' : ''}${formatSize(ds.size)}`}
                actions={
                  <>
                    {localDomains.has(ds.name) && (
                      <button className="btn-downloaded" disabled>DL済み</button>
                    )}
                    <button
                      className="btn-download"
                      disabled={!!downloading[ds.name]}
                      onClick={() => downloadShared(ds)}
                    >
                      {downloading[ds.name] || (localDomains.has(ds.name) ? '更新' : 'ダウンロード')}
                    </button>
                  </>
                }
              />
            ))
          )}
        </section>
      )}
    </div>
  )
}
