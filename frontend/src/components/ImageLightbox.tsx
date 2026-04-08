import type { ImageResult } from '../api/client'

interface Props {
  image: ImageResult
  onClose: () => void
  onOpenPage: (url: string) => void
}

export default function ImageLightbox({ image, onClose, onOpenPage }: Props) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.92)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', zIndex: 2000, padding: 16,
      }}
    >
      <img
        src={image.src}
        alt={image.alt}
        style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain', borderRadius: 12 }}
        onClick={(e) => e.stopPropagation()}
      />
      <div style={{ marginTop: 16, color: '#fff', textAlign: 'center', maxWidth: '600px' }}>
        {image.alt && <div style={{ marginBottom: 6, fontWeight: 600, fontSize: '1em' }}>{image.alt}</div>}
        <div style={{ color: '#aaa', fontSize: 12, marginBottom: 12 }}>{image.page_title || image.domain}</div>
        <div style={{ display: 'flex', gap: 8, justifyContent: 'center' }}>
          <button
            onClick={(e) => { e.stopPropagation(); onClose(); onOpenPage(image.page_url) }}
            className="btn-action"
          >
            ページを開く
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onClose() }}
            className="btn-secondary"
            style={{ background: 'rgba(255,255,255,0.12)', color: '#fff', borderColor: 'rgba(255,255,255,0.2)' }}
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  )
}
