import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import { apiExport, apiImport, apiUploadDataset, apiGetSites, type SiteInfo } from '../api/client'

export default function ManageScreen() {
  const navigate = useNavigate()
  const [importStatus, setImportStatus] = useState('')
  const [uploadDomain, setUploadDomain] = useState('')
  const [uploadStatus, setUploadStatus] = useState('')
  const [sites, setSites] = useState<SiteInfo[]>([])
  const [showUpload, setShowUpload] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  async function handleExportSite() {
    const domain = prompt('エクスポートするドメイン名:')
    if (!domain) return
    try {
      const blob = await apiExport(domain)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${domain}.tar.gz`
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) { alert(e) }
  }

  async function handleImport(file: File) {
    setImportStatus('インポート中...')
    try {
      const r = await apiImport(file)
      if (r.error) { setImportStatus('エラー: ' + r.error); return }
      setImportStatus('完了')
    } catch (e) {
      setImportStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  async function showUploadDialog() {
    try {
      setSites(await apiGetSites())
      setShowUpload(true)
    } catch { /* */ }
  }

  async function uploadSite(domain: string) {
    if (!confirm(`「${domain}」を共有データセットとしてアップロードしますか？`)) return
    setUploadDomain(domain)
    setUploadStatus('アップロード中...')
    try {
      const r = await apiUploadDataset(domain)
      if (r.error) { setUploadStatus('エラー: ' + r.error); return }
      setUploadStatus(`完了: ${r.url}`)
    } catch (e) {
      setUploadStatus('エラー: ' + (e instanceof Error ? e.message : String(e)))
    }
  }

  return (
    <div className="screen">
      <SubHeader title="管理" />

      <section>
        <h2>サイト作成</h2>
        <button className="btn-manage" onClick={() => navigate('/site-builder')} style={{ width: '100%' }}>
          テンプレートからサイトを作成
        </button>
      </section>

      <section>
        <h2>エクスポート</h2>
        <p className="muted" style={{ margin: '0 0 8px' }}>データセットをtar.gzとしてダウンロード</p>
        <button className="btn-action" onClick={handleExportSite} style={{ width: '100%' }}>
          エクスポート
        </button>
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

      <section>
        <h2>アップロード（GitHub共有）</h2>
        <p className="muted" style={{ margin: '0 0 8px' }}>データセットを共有リポジトリにアップロード</p>
        <button className="btn-action" onClick={showUploadDialog} style={{ width: '100%', background: 'var(--ok)' }}>
          アップロードするサイトを選択
        </button>
        {showUpload && sites.length > 0 && (
          <div style={{ marginTop: 8 }}>
            {sites.filter(s => s.has_catalog).map((s) => (
              <div key={s.domain} className="dataset-item">
                <div className="dataset-name">{s.domain}</div>
                <div className="dataset-info">{s.page_count} ページ</div>
                <div className="dataset-actions">
                  <button className="btn-download" onClick={() => uploadSite(s.domain)}>
                    {uploadDomain === s.domain && uploadStatus ? uploadStatus : 'アップロード'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
        {uploadStatus && !showUpload && <p className="muted" style={{ marginTop: 8 }}>{uploadStatus}</p>}
      </section>
    </div>
  )
}
