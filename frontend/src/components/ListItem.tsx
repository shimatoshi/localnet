interface Props {
  title: string
  url: string
  subtitle?: string
  className?: string
  onClick: () => void
}

export default function ListItem({ title, url, subtitle, className = 'history-item', onClick }: Props) {
  return (
    <div className={className} onClick={onClick}>
      <div className={`${className.replace('-item', '')}-title`}>{title || url}</div>
      <div className={`${className.replace('-item', '')}-url`}>{url}</div>
      {subtitle && <div className="history-time">{subtitle}</div>}
    </div>
  )
}
