import { useState, useEffect, useCallback } from 'react'
import SubHeader from '../components/SubHeader'
import { useOnline } from '../hooks/useOnline'
import {
  apiListDatasets, apiListSharedDatasets, apiDownloadSharedDataset,
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

  const loadShared = useCallback(async () => {
    try { setShared(await apiListSharedDatasets()) } catch { /* */ }
  }, [])

  useEffect(() => {
    loadLocal()
    if (online) loadShared()
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
          <h2>共有データセット</h2>
          {shared.length === 0 ? (
            <p className="muted">共有データセットなし</p>
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
