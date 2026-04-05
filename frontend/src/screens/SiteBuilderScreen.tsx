import { useState, useRef, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import SubHeader from '../components/SubHeader'
import { apiGetSitePages } from '../api/client'

interface PageEntry {
  title: string
  slug: string
  body: string
  imageKeys: string[]
  attachmentKeys: string[]
}

function bodyToHtml(body: string): string {
  if (!body) return ''
  return body.split('\n').map((line) => {
    const trimmed = line.trim()
    if (!trimmed) return '<br>'
    if (trimmed.startsWith('## ')) return `<h3>${esc(trimmed.slice(3))}</h3>`
    if (trimmed.startsWith('# ')) return `<h2>${esc(trimmed.slice(2))}</h2>`
    if (trimmed.startsWith('- ')) return `<li>${esc(trimmed.slice(2))}</li>`
    return `<p>${esc(trimmed)}</p>`
  }).join('\n')
}

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function buildPreviewHtml(siteName: string, page: PageEntry, imageUrls: string[]): string {
  const bodyHtml = bodyToHtml(page.body)
  const imagesHtml = imageUrls.map((u) => `<figure><img src="${u}" alt="" style="max-width:100%;border-radius:4px"></figure>`).join('\n')

  return `<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.7;color:#333;background:#fafafa;max-width:800px;margin:0 auto;padding:16px}
h1{font-size:1.5em;margin:16px 0 8px}
h2{font-size:1.3em;margin:20px 0 8px;color:#1a1a2e}
h3{font-size:1.1em;margin:16px 0 6px}
p{margin:6px 0}
li{margin-left:24px}
figure{margin:12px 0}
</style></head><body>
<h1>${esc(page.title || 'タイトル未設定')}</h1>
${bodyHtml}
${imagesHtml}
</body></html>`
}

export default function SiteBuilderScreen() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const datasetName = searchParams.get('dataset')
  const editSite = searchParams.get('edit')
  const [siteName, setSiteName] = useState(editSite || '')
  const [pages, setPages] = useState<PageEntry[]>([
    { title: '', slug: '', body: '', imageKeys: [], attachmentKeys: [] },
  ])
  const [files, setFiles] = useState<Record<string, File>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [previewIdx, setPreviewIdx] = useState(0)
  const [showPreview, setShowPreview] = useState(true)
  const [imageDataUrls, setImageDataUrls] = useState<Record<string, string>>({})
  const fileCounter = useRef(0)

  useEffect(() => {
    if (editSite && datasetName && !loaded) {
      apiGetSitePages(datasetName, editSite).then((data) => {
        if (data.pages && data.pages.length > 0) {
          setPages(data.pages.map((p: { title: string; slug: string; body: string }) => ({
            title: p.title, slug: p.slug, body: p.body,
            imageKeys: [], attachmentKeys: [],
          })))
        }
        setLoaded(true)
      }).catch(() => setLoaded(true))
    }
  }, [editSite, datasetName, loaded])

  // 画像ファイルをdata URLに変換（プレビュー用）
  useEffect(() => {
    const newUrls: Record<string, string> = {}
    const promises: Promise<void>[] = []
    for (const [key, file] of Object.entries(files)) {
      if (file.type.startsWith('image/') && !imageDataUrls[key]) {
        promises.push(
          new Promise((resolve) => {
            const reader = new FileReader()
            reader.onload = () => { newUrls[key] = reader.result as string; resolve() }
            reader.readAsDataURL(file)
          })
        )
      }
    }
    if (promises.length > 0) {
      Promise.all(promises).then(() => {
        setImageDataUrls((prev) => ({ ...prev, ...newUrls }))
      })
    }
  }, [files]) // eslint-disable-line react-hooks/exhaustive-deps

  const currentPage = pages[previewIdx] || pages[0]
  const currentImageUrls = useMemo(() =>
    (currentPage?.imageKeys || []).map((k) => imageDataUrls[k]).filter(Boolean),
    [currentPage?.imageKeys, imageDataUrls]
  )
  const previewHtml = useMemo(() =>
    buildPreviewHtml(siteName, currentPage, currentImageUrls),
    [siteName, currentPage, currentImageUrls]
  )

  function updatePage(idx: number, partial: Partial<PageEntry>) {
    setPages((prev) => prev.map((p, i) => (i === idx ? { ...p, ...partial } : p)))
  }

  function addPage() {
    setPages((prev) => [...prev, { title: '', slug: '', body: '', imageKeys: [], attachmentKeys: [] }])
  }

  function removePage(idx: number) {
    if (pages.length <= 1) return
    setPages((prev) => prev.filter((_, i) => i !== idx))
    if (previewIdx >= pages.length - 1) setPreviewIdx(Math.max(0, pages.length - 2))
  }

  function addFile(pageIdx: number, type: 'image' | 'attachment', fileList: FileList | null) {
    if (!fileList) return
    const newFiles = { ...files }
    const keys: string[] = []
    for (let i = 0; i < fileList.length; i++) {
      const key = `file_${++fileCounter.current}`
      newFiles[key] = fileList[i]
      keys.push(key)
    }
    setFiles(newFiles)
    if (type === 'image') {
      updatePage(pageIdx, { imageKeys: [...pages[pageIdx].imageKeys, ...keys] })
    } else {
      updatePage(pageIdx, { attachmentKeys: [...pages[pageIdx].attachmentKeys, ...keys] })
    }
  }

  function removeFile(pageIdx: number, type: 'image' | 'attachment', key: string) {
    const newFiles = { ...files }
    delete newFiles[key]
    setFiles(newFiles)
    const newDataUrls = { ...imageDataUrls }
    delete newDataUrls[key]
    setImageDataUrls(newDataUrls)
    if (type === 'image') {
      updatePage(pageIdx, { imageKeys: pages[pageIdx].imageKeys.filter((k) => k !== key) })
    } else {
      updatePage(pageIdx, { attachmentKeys: pages[pageIdx].attachmentKeys.filter((k) => k !== key) })
    }
  }

  async function handleSubmit() {
    if (!siteName.trim()) { setError('サイト名を入力してください'); return }
    if (!pages[0].title.trim() && !pages[0].body.trim()) { setError('少なくとも1ページの内容が必要です'); return }
    setError('')
    setSubmitting(true)

    try {
      const siteData = {
        name: siteName,
        pages: pages.map((p, i) => ({
          title: p.title || `Page ${i + 1}`,
          slug: p.slug || `page${i + 1}`,
          body: p.body,
          images: p.imageKeys,
          attachments: p.attachmentKeys,
        })),
      }

      const formData = new FormData()
      formData.append('data', JSON.stringify(siteData))
      for (const [key, file] of Object.entries(files)) {
        formData.append(key, file)
      }

      const endpoint = datasetName
        ? `/api/datasets/${encodeURIComponent(datasetName)}/add-template`
        : '/api/sites/custom/create-from-template'

      const res = await fetch(endpoint, { method: 'POST', body: formData })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`)
      navigate(datasetName ? '/manage' : '/crawl')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="screen">
      <SubHeader title={editSite ? 'サイト編集' : 'サイト作成'}>
        <button className="action-link" onClick={() => setShowPreview(!showPreview)}>
          {showPreview ? '編集のみ' : 'プレビュー'}
        </button>
      </SubHeader>

      {/* プレビュー */}
      {showPreview && (
        <section className="preview-section">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
            <h2 style={{ border: 'none', margin: 0, padding: 0 }}>プレビュー</h2>
            {pages.length > 1 && (
              <div style={{ display: 'flex', gap: 4 }}>
                {pages.map((p, i) => (
                  <button
                    key={i}
                    onClick={() => setPreviewIdx(i)}
                    className={i === previewIdx ? 'btn-action btn-small' : 'btn-small'}
                    style={i !== previewIdx ? { background: 'var(--surface2)', color: 'var(--text)', border: 'none', borderRadius: 4, cursor: 'pointer' } : undefined}
                  >
                    {p.title || `P${i + 1}`}
                  </button>
                ))}
              </div>
            )}
          </div>
          <iframe
            srcDoc={previewHtml}
            sandbox="allow-same-origin"
            style={{
              width: '100%', height: 300, border: '1px solid var(--surface2)',
              borderRadius: 6, background: '#fff',
            }}
          />
        </section>
      )}

      <section>
        <label className="builder-label">
          サイト名
          <input type="text" value={siteName} onChange={(e) => setSiteName(e.target.value)}
                 placeholder="my-site" disabled={!!editSite} />
        </label>
      </section>

      {pages.map((page, idx) => (
        <section key={idx} className="builder-page">
          <div className="builder-page-header">
            <h2>ページ {idx + 1}</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              {pages.length > 1 && (
                <button className="btn-delete" onClick={() => removePage(idx)}>削除</button>
              )}
            </div>
          </div>

          <label className="builder-label">
            タイトル
            <input type="text" value={page.title}
                   onChange={(e) => { updatePage(idx, { title: e.target.value }); setPreviewIdx(idx) }}
                   placeholder="ページタイトル" />
          </label>

          <label className="builder-label">
            スラッグ (URL)
            <input type="text" value={page.slug}
                   onChange={(e) => updatePage(idx, { slug: e.target.value })}
                   placeholder={idx === 0 ? 'index (トップページ)' : 'about'} />
          </label>

          <label className="builder-label">
            本文
            <textarea value={page.body}
                      onChange={(e) => { updatePage(idx, { body: e.target.value }); setPreviewIdx(idx) }}
                      placeholder={"本文を入力...\n# で見出し\n## で小見出し\n- で箇条書き"}
                      rows={8} />
          </label>

          <div className="builder-files">
            <div className="builder-file-section">
              <label className="btn-action btn-small">
                画像を追加
                <input type="file" accept="image/*" multiple hidden
                       onChange={(e) => { addFile(idx, 'image', e.target.files); setPreviewIdx(idx) }} />
              </label>
              {page.imageKeys.map((key) => (
                <span key={key} className="file-chip">
                  {imageDataUrls[key] && <img src={imageDataUrls[key]} alt="" style={{ height: 20, borderRadius: 2 }} />}
                  {files[key]?.name || key}
                  <button onClick={() => removeFile(idx, 'image', key)}>&times;</button>
                </span>
              ))}
            </div>

            <div className="builder-file-section">
              <label className="btn-action btn-small">
                添付ファイルを追加
                <input type="file" multiple hidden
                       onChange={(e) => addFile(idx, 'attachment', e.target.files)} />
              </label>
              {page.attachmentKeys.map((key) => (
                <span key={key} className="file-chip">
                  {files[key]?.name || key}
                  <button onClick={() => removeFile(idx, 'attachment', key)}>&times;</button>
                </span>
              ))}
            </div>
          </div>
        </section>
      ))}

      <section>
        <button className="btn-action" onClick={addPage} style={{ width: '100%' }}>
          + ページを追加
        </button>
      </section>

      {error && <p style={{ color: 'var(--warn)', padding: '0 16px' }}>{error}</p>}

      <section style={{ paddingBottom: 80 }}>
        <button className="btn-action" onClick={handleSubmit} disabled={submitting}
                style={{ width: '100%', padding: '12px', fontSize: '1.1em' }}>
          {submitting ? '保存中...' : editSite ? 'サイトを保存' : 'サイトを作成'}
        </button>
      </section>
    </div>
  )
}
