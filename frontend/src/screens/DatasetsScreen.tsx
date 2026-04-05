import { useState, useEffect, useCallback } from 'react'
import SubHeader from '../components/SubHeader'
import { useOnline } from '../hooks/useOnline'
import {
  apiListDatasets, apiListSharedDatasets, apiRefreshSharedDatasets,
  apiDownloadSharedDataset,
  type DatasetInfo, type SharedDataset,
} from '../api/client'

export default function DatasetsScreen() {
  const online = useOnline()
  const [localDatasets, setLocalDatasets] = useState<DatasetInfo[]>([])
  const [shared, setShared] = useState<SharedDataset[]>([])
  const [downloading, setDownloading] = useState<Record<string, string>>({})

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
    loadLocal()
    if (online) loadShared()  // 保存済みリストを読み込み
  }, [online, loadLocal, loadShared])

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

  return (
    <div className="screen">
      <SubHeader title="Datasets" />

      <section>
        <h2>ローカル</h2>
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
