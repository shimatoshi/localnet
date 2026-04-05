import SubHeader from '../components/SubHeader'
import LogArea from '../components/LogArea'
import { useOnline } from '../hooks/useOnline'
import { useCrawl } from '../hooks/useCrawl'

export default function CrawlScreen() {
  const online = useOnline()
  const {
    sites, showLog, logs,
    doResume, doRecrawl, doBuild, doDelete,
  } = useCrawl(online)

  if (!online) {
    return (
      <div className="screen">
        <SubHeader title="Crawl" />
        <p className="muted" style={{ padding: '40px 16px', textAlign: 'center' }}>サーバーに接続してください</p>
      </div>
    )
  }

  return (
    <div className="screen">
      <SubHeader title="Crawl" />

      <section>
        <div style={{ padding: '12px 0', opacity: 0.6 }}>
          <p style={{ margin: '0 0 8px' }}>クロール機能（実装予定）</p>
          <p className="muted" style={{ margin: 0, fontSize: '0.85em' }}>サーバー経由でクロールを実行します。アプリ内クローラーは今後対応予定です。</p>
        </div>
        <div className="input-row" style={{ opacity: 0.4, pointerEvents: 'none' }}>
          <input type="text" placeholder="URL" disabled />
          <button disabled>設定</button>
        </div>
      </section>

      <section style={{ marginTop: 12 }}>
        <h2>クロール済みサイト</h2>
        <div id="sites-list">
          {sites.length === 0 ? (
            <p className="muted">なし</p>
          ) : (
            sites.map((site) => (
              <div key={site.domain} className="site-item">
                <div className="site-domain">{site.domain}</div>
                <div className="site-stats">{site.file_count} ファイル</div>
                <div className="site-actions">
                  <button className="btn-resume" onClick={() => doResume(site.domain)}>再開</button>
                  {site.has_catalog ? (
                    <>
                      <button className="btn-downloaded" disabled>&#10003; {site.page_count} ページ</button>
                      <button className="btn-build" onClick={() => doBuild(site.domain)}>再生成</button>
                    </>
                  ) : (
                    <button className="btn-build" onClick={() => doBuild(site.domain)}>カタログ生成</button>
                  )}
                  <button className="btn-recrawl" onClick={() => doRecrawl(site.domain)}>再クロール</button>
                  <button className="btn-delete" onClick={() => doDelete(site.domain)}>削除</button>
                </div>
              </div>
            ))
          )}
        </div>
      </section>

      {showLog && (
        <section>
          <h2>ログ</h2>
          <LogArea logs={logs} />
        </section>
      )}
    </div>
  )
}
