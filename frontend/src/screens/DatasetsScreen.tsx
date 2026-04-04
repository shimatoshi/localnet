import SubHeader from '../components/SubHeader'
import { useOnline } from '../hooks/useOnline'
import { useDatasets } from '../hooks/useDatasets'

export default function DatasetsScreen() {
  const online = useOnline()
  const { serverSites, localCatalogs, downloading, downloadDataset, removeLocal } = useDatasets(online)

  const localDomains = new Set(localCatalogs.map((c) => c.domain))

  return (
    <div className="screen">
      <SubHeader title="Datasets" />

      {!online && <p className="muted" style={{ padding: '8px 16px' }}>オフライン</p>}

      {online && (
        <section style={{ marginTop: 0 }}>
          <h2>サーバー</h2>
          {serverSites.length === 0 ? (
            <p className="muted">データセットなし</p>
          ) : (
            serverSites.map((site) => (
              <div key={site.domain} className="dataset-item">
                <div className="dataset-name">{site.domain}</div>
                <div className="dataset-info">{site.page_count} ページ / {site.file_count} ファイル</div>
                <div className="dataset-actions">
                  {localDomains.has(site.domain) && (
                    <button className="btn-downloaded" disabled>&#10003; DL済み</button>
                  )}
                  <button
                    className="btn-download"
                    disabled={!!downloading[site.domain]}
                    onClick={() => downloadDataset(site.domain)}
                  >
                    {downloading[site.domain] || (localDomains.has(site.domain) ? '更新' : 'ダウンロード')}
                  </button>
                </div>
              </div>
            ))
          )}
        </section>
      )}

      <section style={{ marginTop: 12 }}>
        <h2>ダウンロード済み</h2>
        {localCatalogs.length === 0 ? (
          <p className="muted">なし</p>
        ) : (
          localCatalogs.map((cat) => (
            <div key={cat.domain} className="dataset-item">
              <div className="dataset-name">{cat.domain}</div>
              <div className="dataset-info">
                {cat.entries.length} ページ / {new Date(cat.downloadedAt).toLocaleDateString()}
              </div>
              <div className="dataset-actions">
                <button className="btn-delete" onClick={() => removeLocal(cat.domain)}>削除</button>
              </div>
            </div>
          ))
        )}
      </section>
    </div>
  )
}
