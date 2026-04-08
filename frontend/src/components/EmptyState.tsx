interface Props {
  message: string
}

export default function EmptyState({ message }: Props) {
  return (
    <p className="muted" style={{ padding: '40px 16px', textAlign: 'center' }}>
      {message}
    </p>
  )
}
