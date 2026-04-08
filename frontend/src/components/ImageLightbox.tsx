import type { ImageResult } from '../api/client'

interface Props {
  image: ImageResult
  onClose: () => void
  onOpenPage: (url: string) => void
}

export default function ImageLightbox({ image, onClose, onOpenPage }: Props) {
  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <img
        src={image.src}
        alt={image.alt}
        onClick={(e) => e.stopPropagation()}
      />
      <div className="lightbox-info">
        {image.alt && <div className="lightbox-title">{image.alt}</div>}
        <div className="lightbox-subtitle">{image.page_title || image.domain}</div>
        <div className="lightbox-actions">
          <button
            onClick={(e) => { e.stopPropagation(); onClose(); onOpenPage(image.page_url) }}
            className="btn-action"
          >
            ページを開く
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); onClose() }}
            className="btn-secondary lightbox-close"
          >
            閉じる
          </button>
        </div>
      </div>
    </div>
  )
}
