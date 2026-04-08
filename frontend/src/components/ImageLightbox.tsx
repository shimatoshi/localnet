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
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.9)',
        backdropFilter: 'blur(10px)',
        display: 'flex', flexDirection: 'column', alignItems: 'center',
        justifyContent: 'center', zIndex: 2000, padding: 24,
      }}
    >
      <img
        src={image.src}
        alt={image.alt}
        style={{ maxWidth: '100%', maxHeight: '75vh', objectFit: 'contain', borderRadius: 16, boxShadow: '0 20px 50px rgba(0,0,0,0.5)' }}
        onClick={(e) => e.stopPropagation()}
      />
      <div style={{ marginTop: 20, color: '#fff', textAlign: 'center', maxWidth: '600px' }}>
        {image.alt && <div style={{ marginBottom: 8, fontWeight: 600, fontSize: '1.1em' }}>{image.alt}</div>}
        <div style={{ color: '#ccc', fontSize: 13, marginBottom: 16 }}>{image.page_title || image.domain}</div>
        <div style={{ display: 'flex', gap: 12, justifyContent: 'center' }}>
          <button
            onClick={(e) => { e.stopPropagation(); onClose(); onOpenPage(image.page_url) }}
            className="btn-action"
          >
            ページを開く
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onClose() }}
            className="btn-action"
            style={{ background: 'rgba(255,255,255,0.1)' }}
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  )
}
