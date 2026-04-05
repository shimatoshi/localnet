import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import {
  apiListDatasets, apiCreateDataset, apiDeleteDataset,
  apiGetDataset, apiRemoveSiteFromDataset, apiAddCrawledToDataset,
  apiExportDataset, apiImportDataset, apiUploadDataset, apiGetSites,
  type DatasetInfo, type DatasetSite, type SiteInfo,
} from '../api/client'

export default function ManageScreen() {
  const navigate = useNavigate()
  const [datasets, setDatasets] = useState<DatasetInfo[]>([])
  const [selected, setSelected] = useState<DatasetInfo | null>(null)
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [crawledSites, setCrawledSites] = useState<SiteInfo[]>([])
  const [showAddCrawled, setShowAddCrawled] = useState(false)
  const [importStatus, setImportStatus] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const importRef = useRef<HTMLInputElement>(null)

  const loadDatasets = useCallback(async () => {
    try { setDatasets(await apiListDatasets()) } catch { /* */ }
  }, [])

  useEffect(() => { loadDatasets() }, [loadDatasets])

  async function createDataset() {
    if (!newName.trim()) return
    try {
      const r = await apiCreateDataset(newName, newDesc)
      if (r.error) { alert(r.error); return }
      setNewName('')
      setNewDesc('')
      setShowCreate(false)
      loadDatasets()
    } catch (e) { alert(e) }
  }

  async function openDataset(name: string) {
    try {
      const ds = await apiGetDataset(name)
      setSelected(ds)
    } catch (e) { alert(e) }
  }

  async function deleteDataset(name: string) {
    if (!confirm(`データセット「${name}」を削除しますか？`)) return
    await apiDeleteDataset(name)
    setSelected(null)
    loadDatasets()
  }

  async function removeSite(siteName: string) {
    if (!selected) return
    if (!confirm(`「${siteName}」を削除しますか？`)) return
    await apiRemoveSiteFromDataset(selected.name, siteName)
    openDataset(selected.name)
    loadDatasets()
  }

  async function showAddCrawledDialog() {
    try {
      const sites = await apiGetSites()
      setCrawledSites(sites.filter(s => s.has_catalog))
      setShowAddCrawled(true)
    } catch { /* */ }
  }

  async function addCrawled(domain: string) {
    if (!selected) return
    const r = await apiAddCrawledToDataset(selected.name, domain)
    if (r.error) { alert(r.error); return }
    setShowAddCrawled(false)
    openDataset(selected.name)
    loadDatasets()
  }

  async function exportDataset() {
    if (!selected) return
    try {
      const blob = await apiExportDataset(selected.name)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selected.name}.tar.gz`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { alert(e) }
  }

  async function uploadDataset() {
    if (!selected) return
    if (!confirm(`「${selected.name}」を共有データセットとしてアップロードしますか？`)) return
    setUploadStatus('アップロード中...')
    try {
      const r = await apiUploadDataset(selected.name)
      if (r.error) { setUploadStatus('エラー: ' + r.error); return }
      setUploadStatus(`完了: ${r.url}`)
    } catch (e) {
      setUploadStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function handleImport(file: File) {
    setImportStatus('インポート中...')
    try {
      const r = await apiImportDataset(file)
      if (r.error) { setImportStatus('エラー: ' + r.error); return }
      setImportStatus(`完了: ${r.name}`)
      loadDatasets()
    } catch (e) {
      setImportStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  // === データセット詳細ビュー ===
  if (selected) {
    return (
      <div className="screen">
        <SubHeader title={selected.name} />

        <section>
          <p className="muted">{selected.description || '説明なし'}</p>
          <p className="muted" style={{ fontSize: '0.8em' }}>作成: {selected.created_at}</p>
        </section>

        <section>
          <h2>サイト</h2>
          {selected.sites.length === 0 ? (
            <p className="muted">サイトなし</p>
          ) : (
            selected.sites.map((site) => (
              <div key={site.name} className="dataset-item">
                <div className="dataset-name">
                  {site.name}
                  <span className="muted" style={{ fontSize: '0.8em', marginLeft: 8 }}>
                    {site.source === 'crawled' ? '(クロール)' : '(自作)'}
                  </span>
                </div>
                <div className="dataset-info">{site.page_count} ページ / {site.file_count} ファイル</div>
                <div className="dataset-actions">
                  {site.source === 'custom' && (
                    <button className="btn-build" onClick={() => navigate(`/site-builder?dataset=${selected.name}&edit=${site.name}`)}>編集</button>
                  )}
                  <button className="btn-delete" onClick={() => removeSite(site.name)}>削除</button>
                </div>
              </div>
            ))
          )}
        </section>

        <section>
          <h2>サイトを追加</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn-action" onClick={() => navigate(`/site-builder?dataset=${selected.name}`)}>
              テンプレートから作成
            </button>
            <button className="btn-action" onClick={showAddCrawledDialog} style={{ background: 'var(--ok)' }}>
              クロール済みを追加
            </button>
          </div>
        </section>

        {showAddCrawled && (
          <section>
            <h2>クロール済みサイト</h2>
            {crawledSites.length === 0 ? (
              <p className="muted">なし</p>
            ) : (
              crawledSites.map((s) => (
                <div key={s.domain} className="dataset-item">
                  <div className="dataset-name">{s.domain}</div>
                  <div className="dataset-info">{s.page_count} ページ</div>
                  <div className="dataset-actions">
                    <button className="btn-download" onClick={() => addCrawled(s.domain)}>追加</button>
                  </div>
                </div>
              ))
            )}
            <button className="muted" onClick={() => setShowAddCrawled(false)} style={{ marginTop: 8, border: 'none', background: 'none', cursor: 'pointer' }}>閉じる</button>
          </section>
        )}

        <section>
          <h2>操作</h2>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn-action" onClick={uploadDataset} style={{ background: 'var(--ok)' }}>
              アップロード
            </button>
            <button className="btn-action" onClick={exportDataset} style={{ background: 'var(--surface2)', color: 'var(--text)' }}>
              エクスポート
            </button>
            <button className="btn-action" onClick={() => deleteDataset(selected.name)} style={{ background: 'var(--err)' }}>
              データセットを削除
            </button>
          </div>
          {uploadStatus && <p className="muted" style={{ marginTop: 8 }}>{uploadStatus}</p>}
        </section>

        <div style={{ padding: '16px' }}>
          <button onClick={() => { setSelected(null); loadDatasets() }} style={{ border: 'none', background: 'none', color: 'var(--accent)', cursor: 'pointer' }}>
            ← データセット一覧に戻る
          </button>
        </div>
      </div>
    )
  }

  // === データセット一覧ビュー ===
  return (
    <div className="screen">
      <SubHeader title="管理">
        <button className="action-link" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? '閉じる' : '+ 作成'}
        </button>
      </SubHeader>

      {showCreate && (
        <section>
          <h2>データセットを作成</h2>
          <div className="builder-label">
            名前
            <input type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
                   placeholder="データセット名" style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 12px', border: '1px solid var(--surface2)', borderRadius: 6, background: 'var(--bg)', color: 'var(--text)', fontSize: 15 }} />
          </div>
          <div className="builder-label" style={{ marginTop: 8 }}>
            説明 (任意)
            <input type="text" value={newDesc} onChange={(e) => setNewDesc(e.target.value)}
                   placeholder="格闘技サイトまとめ" style={{ display: 'block', width: '100%', marginTop: 4, padding: '8px 12px', border: '1px solid var(--surface2)', borderRadius: 6, background: 'var(--bg)', color: 'var(--text)', fontSize: 15 }} />
          </div>
          <button className="btn-action" onClick={createDataset} style={{ marginTop: 8 }}>作成</button>
        </section>
      )}

      <section>
        <h2>データセット</h2>
        {datasets.length === 0 ? (
          <p className="muted">データセットなし</p>
        ) : (
          datasets.map((ds) => (
            <div key={ds.name} className="dataset-item" onClick={() => openDataset(ds.name)} style={{ cursor: 'pointer' }}>
              <div className="dataset-name">{ds.name}</div>
              <div className="dataset-info">
                {ds.description && <span>{ds.description} / </span>}
                {ds.site_count} サイト
              </div>
            </div>
          ))
        )}
      </section>

      <section>
        <h2>インポート</h2>
        <p className="muted" style={{ margin: '0 0 8px' }}>tar.gz / zip からデータセットとして読み込み</p>
        <label className="btn-import-label">
          ファイルを選択
          <input ref={importRef} type="file" accept=".tar.gz,.tgz,.tar,.zip" hidden
                 onChange={(e) => {
                   const f = e.target.files?.[0]
                   if (f) handleImport(f)
                   e.target.value = ''
                 }} />
        </label>
        {importStatus && <p className="muted" style={{ marginTop: 8 }}>{importStatus}</p>}
      </section>
    </div>
  )
}
