interface Props {
  message?: string
}

export default function LoadingSpinner({ message = '読み込み中...' }: Props) {
  return (
    <div style={{ padding: '40px 0', textAlign: 'center' }}>
      <div className="loading-spinner"></div>
      <p className="muted" style={{ marginTop: 16 }}>{message}</p>
    </div>
  )
}
