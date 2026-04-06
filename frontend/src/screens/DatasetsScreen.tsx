import { useState, useEffect, useCallback } from 'react'
import SubHeader from '../components/SubHeader'
import { useOnline } from '../hooks/useOnline'
import {
  apiGetSites, apiListDatasets, apiListSharedDatasets, apiRefreshSharedDatasets,
  apiDownloadSharedDataset, apiBuild, apiDeleteSite,
  type SiteInfo, type DatasetInfo, type SharedDataset,
} from '../api/client'

export default function DatasetsScreen() {
  const online = useOnline()
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [localDatasets, setLocalDatasets] = useState<DatasetInfo[]>([])
  const [shared, setShared] = useState<SharedDataset[]>([])
  const [downloading, setDownloading] = useState<Record<string, string>>({})

  const loadSites = useCallback(async () => {
    try { setSites(await apiGetSites()) } catch { /* */ }
  }, [])

  const loadLocal = useCallback(async () => {
    try { setLocalDatasets(await apiListDatasets()) } catch { /* */ }
  }, [])

  const [loadingShared, setLoadingShared] = useState(false)

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
    loadLocal()
    if (online) loadShared()
  }, [online, loadSites, loadLocal, loadShared])

  const localNames = new Set(localDatasets.map(d => d.name))

  async function downloadShared(ds: SharedDataset) {
    setDownloading(prev => ({ ...prev, [ds.name]: 'ダウンロード中...' }))
    try {
      const r = await apiDownloadSharedDataset(ds.name, ds.download_url)
      if (r.error) {
        setDownloading(prev => ({ ...prev, [ds.name]: 'エラー: ' + r.error }))
        return
      }
      setDownloading(prev => ({ ...prev, [ds.name]: '完了' }))
      loadLocal()
    } catch (e) {
      setDownloading(prev => ({ ...prev, [ds.name]: 'エラー' }))
    }
  }

  function formatSize(bytes: number) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  async function doBuild(domain: string) {
    try {
      await apiBuild(domain)
      loadSites()
    } catch { /* */ }
  }

  async function doDelete(domain: string) {
    if (!confirm(`${domain} を削除しますか？`)) return
    try {
      await apiDeleteSite(domain)
      loadSites()
    } catch { /* */ }
  }

  return (
    <div className="screen">
      <SubHeader title="Datasets" />

      <section>
        <h2>クロール済みサイト</h2>
        {sites.length === 0 ? (
          <p className="muted">なし — Crawlタブからサイトを取り込めます</p>
        ) : (
          sites.map((site) => (
            <div key={site.domain} className="site-item">
              <div className="site-domain">{site.domain}</div>
              <div className="site-stats">{site.file_count} ファイル</div>
              <div className="site-actions">
                {site.has_catalog ? (
                  <>
                    <button className="btn-downloaded" disabled>&#10003; {site.page_count} ページ</button>
                    <button className="btn-build" onClick={() => doBuild(site.domain)}>再生成</button>
                  </>
                ) : (
                  <button className="btn-build" onClick={() => doBuild(site.domain)}>カタログ生成</button>
                )}
                <button className="btn-delete" onClick={() => doDelete(site.domain)}>削除</button>
              </div>
            </div>
          ))
        )}
      </section>

      <section>
        <h2>データセット</h2>
        {localDatasets.length === 0 ? (
          <p className="muted">データセットなし — 管理タブから作成できます</p>
        ) : (
          localDatasets.map((ds) => (
            <div key={ds.name} className="dataset-item">
              <div className="dataset-name">{ds.name}</div>
              <div className="dataset-info">
                {ds.description && <span>{ds.description} / </span>}
                {ds.site_count} サイト
              </div>
            </div>
          ))
        )}
      </section>

      {online && (
        <section>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <h2 style={{ border: 'none', margin: 0, padding: 0 }}>共有データセット</h2>
            <button className="btn-action btn-small" onClick={refreshShared} disabled={loadingShared}>
              {loadingShared ? '取得中...' : '更新'}
            </button>
          </div>
          {shared.length === 0 ? (
            <p className="muted" style={{ marginTop: 8 }}>{loadingShared ? '取得中...' : '「更新」を押して最新の共有データセットを取得'}</p>
          ) : (
            shared.map((ds) => (
              <div key={ds.name + ds.tag} className="dataset-item">
                <div className="dataset-name">{ds.name}</div>
                <div className="dataset-info">
                  {ds.description && <span>{ds.description} / </span>}
                  {formatSize(ds.size)}
                </div>
                <div className="dataset-actions">
                  {localNames.has(ds.name) && (
                    <button className="btn-downloaded" disabled>DL済み</button>
                  )}
                  <button
                    className="btn-download"
                    disabled={!!downloading[ds.name]}
                    onClick={() => downloadShared(ds)}
                  >
                    {downloading[ds.name] || (localNames.has(ds.name) ? '更新' : 'ダウンロード')}
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      )}
    </div>
  )
}
