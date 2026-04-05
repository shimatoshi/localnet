import { useState, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import SubHeader from '../components/SubHeader'

interface PageEntry {
  title: string
  slug: string
  body: string
  imageKeys: string[]
  attachmentKeys: string[]
}

export default function SiteBuilderScreen() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const datasetName = searchParams.get('dataset')
  const [siteName, setSiteName] = useState('')
  const [pages, setPages] = useState<PageEntry[]>([
    { title: '', slug: '', body: '', imageKeys: [], attachmentKeys: [] },
  ])
  const [files, setFiles] = useState<Record<string, File>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const fileCounter = useRef(0)

  function updatePage(idx: number, partial: Partial<PageEntry>) {
    setPages((prev) => prev.map((p, i) => (i === idx ? { ...p, ...partial } : p)))
  }

  function addPage() {
    setPages((prev) => [...prev, { title: '', slug: '', body: '', imageKeys: [], attachmentKeys: [] }])
  }

  function removePage(idx: number) {
    if (pages.length <= 1) return
    setPages((prev) => prev.filter((_, i) => i !== idx))
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
      <SubHeader title="サイト作成" />

      <section>
        <label className="builder-label">
          サイト名
          <input
            type="text"
            value={siteName}
            onChange={(e) => setSiteName(e.target.value)}
            placeholder="my-site"
          />
        </label>
      </section>

      {pages.map((page, idx) => (
        <section key={idx} className="builder-page">
          <div className="builder-page-header">
            <h2>ページ {idx + 1}</h2>
            {pages.length > 1 && (
              <button className="btn-delete" onClick={() => removePage(idx)}>削除</button>
            )}
          </div>

          <label className="builder-label">
            タイトル
            <input
              type="text"
              value={page.title}
              onChange={(e) => updatePage(idx, { title: e.target.value })}
              placeholder="ページタイトル"
            />
          </label>

          <label className="builder-label">
            スラッグ (URL)
            <input
              type="text"
              value={page.slug}
              onChange={(e) => updatePage(idx, { slug: e.target.value })}
              placeholder={idx === 0 ? 'index (トップページ)' : 'about'}
            />
          </label>

          <label className="builder-label">
            本文
            <textarea
              value={page.body}
              onChange={(e) => updatePage(idx, { body: e.target.value })}
              placeholder={"本文を入力...\n# で見出し\n## で小見出し\n- で箇条書き"}
              rows={8}
            />
          </label>

          <div className="builder-files">
            <div className="builder-file-section">
              <label className="btn-action btn-small">
                画像を追加
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  hidden
                  onChange={(e) => addFile(idx, 'image', e.target.files)}
                />
              </label>
              {page.imageKeys.map((key) => (
                <span key={key} className="file-chip">
                  {files[key]?.name || key}
                  <button onClick={() => removeFile(idx, 'image', key)}>&times;</button>
                </span>
              ))}
            </div>

            <div className="builder-file-section">
              <label className="btn-action btn-small">
                添付ファイルを追加
                <input
                  type="file"
                  multiple
                  hidden
                  onChange={(e) => addFile(idx, 'attachment', e.target.files)}
                />
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
        <button
          className="btn-action"
          onClick={handleSubmit}
          disabled={submitting}
          style={{ width: '100%', padding: '12px', fontSize: '1.1em' }}
        >
          {submitting ? '作成中...' : 'サイトを作成'}
        </button>
      </section>
    </div>
  )
}
