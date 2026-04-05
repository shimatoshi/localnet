import { useNavigate } from 'react-router-dom'

interface Props {
  title: string
  action?: { label: string; onClick: () => void }
  children?: React.ReactNode
}

export default function SubHeader({ title, action, children }: Props) {
  const navigate = useNavigate()

  return (
    <div className="sub-header">
      <button className="back-btn" onClick={() => navigate('/')}>&larr;</button>
      <h2>{title}</h2>
      {action && (
        <button className="action-link" onClick={action.onClick}>{action.label}</button>
      )}
      {children}
    </div>
  )
}
