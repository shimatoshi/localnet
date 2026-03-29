// ページビュアー — iframe srcdocで表示（画像オフライン対応）

window.openViewer = async function(datasetName, pageId, url) {
  $('viewer-url').textContent = url || '';
  $('viewer-frame').srcdoc = '<p style="color:#888;padding:20px">読み込み中...</p>';
  revokeViewerBlobs();
  switchTab('tab-viewer');

  try {
    const page = await getPage(datasetName, pageId);
    if (!page) {
      $('viewer-frame').srcdoc = '<p style="color:#888;padding:20px">ページが見つかりません</p>';
      return;
    }

    let html = page.html;

    // localnet://img/{id} をBlobURLに変換
    const imgPattern = /localnet:\/\/img\/(\d+)/g;
    const imgIds = new Set();
    let m;
    while ((m = imgPattern.exec(html)) !== null) {
      imgIds.add(parseInt(m[1]));
    }

    if (imgIds.size > 0) {
      const blobUrls = await resolveImages(datasetName, Array.from(imgIds));
      for (const [id, blobUrl] of Object.entries(blobUrls)) {
        html = html.replaceAll(`localnet://img/${id}`, blobUrl);
      }
    }

    // <base>タグ挿入
    const baseUrl = page.url.replace(/[^/]*$/, '');
    html = html.replace(/<head([^>]*)>/i, `<head$1><base href="${escHtml(baseUrl)}">`);

    // リンクインターセプト + 画像クリーンアップ用スクリプト注入
    const interceptScript = `
      <script>
        document.addEventListener('click', function(e) {
          const a = e.target.closest('a');
          if (!a) return;
          e.preventDefault();
          const href = a.href;
          if (href) {
            window.parent.postMessage({ type: 'navigate', url: href }, '*');
          }
        });
      </script>
    `;
    html = html.replace('</body>', interceptScript + '</body>');

    $('viewer-frame').srcdoc = html;
  } catch (e) {
    $('viewer-frame').srcdoc = `<p style="color:#888;padding:20px">エラー: ${e.message}</p>`;
  }
};

window.closeViewer = function() {
  // BlobURL解放
  revokeViewerBlobs();
  $('viewer-frame').srcdoc = '';
  switchTab(currentTab);
};

// BlobURL管理
let _viewerBlobUrls = [];

function revokeViewerBlobs() {
  for (const url of _viewerBlobUrls) {
    URL.revokeObjectURL(url);
  }
  _viewerBlobUrls = [];
}

async function resolveImages(datasetName, imgIds) {
  revokeViewerBlobs();
  const db = await openDataset(datasetName);
  if (!db) return {};

  const result = {};
  for (const id of imgIds) {
    try {
      const stmt = db.prepare('SELECT data, mime FROM images WHERE id = ?');
      stmt.bind([id]);
      if (stmt.step()) {
        const row = stmt.getAsObject(null);
        const data = row['data'];
        const mime = row['mime'] || 'image/jpeg';
        if (data instanceof Uint8Array) {
          const blob = new Blob([data], { type: mime });
          const blobUrl = URL.createObjectURL(blob);
          _viewerBlobUrls.push(blobUrl);
          result[id] = blobUrl;
        }
      }
      stmt.free();
    } catch (e) {
      console.warn('Image resolve error:', id, e);
    }
  }
  return result;
}

// iframeからのリンクナビゲーションを処理
window.addEventListener('message', async (e) => {
  if (!e.data || e.data.type !== 'navigate') return;
  const url = e.data.url;

  const found = await findPageByUrl(url);
  if (found) {
    openViewer(found.dataset, found.id, url);
  } else {
    const variations = [
      url.replace(/\/$/, '/index.html'),
      url + '.html',
      url.replace(/\.html$/, ''),
    ];
    for (const v of variations) {
      const f = await findPageByUrl(v);
      if (f) {
        openViewer(f.dataset, f.id, v);
        return;
      }
    }
    $('viewer-frame').srcdoc = `
      <div style="color:#888;padding:20px;font-family:sans-serif">
        <p>このページはローカルにありません</p>
        <p style="font-size:0.85em;margin-top:8px;word-break:break-all">${escHtml(url)}</p>
      </div>
    `;
  }
});
