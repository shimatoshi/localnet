import type { SiteInfo } from '../api/client'

interface Props {
  site: SiteInfo
  actions: React.ReactNode
  badge?: React.ReactNode
}

export default function SiteItem({ site, actions, badge }: Props) {
  return (
    <div className="site-item">
      <div className="site-domain">
        {site.domain}
        {badge}
      </div>
      <div className="site-stats">
        {site.page_count !== undefined && `${site.page_count} ページ / `}
        {site.file_count} ファイル
      </div>
      <div className="site-actions">{actions}</div>
    </div>
  )
}
