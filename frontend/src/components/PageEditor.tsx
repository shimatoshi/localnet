interface PageEntry {
  title: string
  slug: string
  body: string
  imageKeys: string[]
  attachmentKeys: string[]
}

interface Props {
  page: PageEntry
  index: number
  canRemove: boolean
  files: Record<string, File>
  imageDataUrls: Record<string, string>
  onUpdate: (index: number, partial: Partial<PageEntry>) => void
  onRemove: (index: number) => void
  onAddFile: (index: number, type: 'image' | 'attachment', files: FileList | null) => void
  onRemoveFile: (index: number, type: 'image' | 'attachment', key: string) => void
  onPreview: (index: number) => void
}

export default function PageEditor({
  page, index, canRemove, files, imageDataUrls,
  onUpdate, onRemove, onAddFile, onRemoveFile, onPreview,
}: Props) {
  return (
    <section className="builder-page">
      <div className="builder-page-header">
        <h2>ページ {index + 1}</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          {canRemove && (
            <button className="btn-delete" onClick={() => onRemove(index)}>削除</button>
          )}
        </div>
      </div>

      <label className="builder-label">
        タイトル
        <input type="text" value={page.title}
               onChange={(e) => { onUpdate(index, { title: e.target.value }); onPreview(index) }}
               placeholder="ページタイトル" />
      </label>

      <label className="builder-label">
        スラッグ (URL)
        <input type="text" value={page.slug}
               onChange={(e) => onUpdate(index, { slug: e.target.value })}
               placeholder={index === 0 ? 'index (トップページ)' : 'about'} />
      </label>

      <label className="builder-label">
        本文
        <textarea value={page.body}
                  onChange={(e) => { onUpdate(index, { body: e.target.value }); onPreview(index) }}
                  placeholder={"本文を入力...\n# で見出し\n## で小見出し\n- で箇条書き"}
                  rows={8} />
      </label>

      <div className="builder-files">
        <div className="builder-file-section">
          <label className="btn-action btn-small">
            画像を追加
            <input type="file" accept="image/*" multiple hidden
                   onChange={(e) => { onAddFile(index, 'image', e.target.files); onPreview(index) }} />
          </label>
          {page.imageKeys.map((key) => (
            <span key={key} className="file-chip">
              {imageDataUrls[key] && <img src={imageDataUrls[key]} alt="" style={{ height: 20, borderRadius: 2 }} />}
              {files[key]?.name || key}
              <button onClick={() => onRemoveFile(index, 'image', key)}>&times;</button>
            </span>
          ))}
        </div>

        <div className="builder-file-section">
          <label className="btn-action btn-small">
            添付ファイルを追加
            <input type="file" multiple hidden
                   onChange={(e) => onAddFile(index, 'attachment', e.target.files)} />
          </label>
          {page.attachmentKeys.map((key) => (
            <span key={key} className="file-chip">
              {files[key]?.name || key}
              <button onClick={() => onRemoveFile(index, 'attachment', key)}>&times;</button>
            </span>
          ))}
        </div>
      </div>
    </section>
  )
}

export type { PageEntry }
