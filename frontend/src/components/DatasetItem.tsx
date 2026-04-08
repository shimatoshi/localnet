interface Props {
  name: string
  info: string
  actions: React.ReactNode
}

export default function DatasetItem({ name, info, actions }: Props) {
  return (
    <div className="dataset-item">
      <div className="dataset-name">{name}</div>
      <div className="dataset-info">{info}</div>
      <div className="dataset-actions">{actions}</div>
    </div>
  )
}
