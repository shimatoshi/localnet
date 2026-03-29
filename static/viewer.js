// ブラウザビュアー — 全画面iframe + 画像オフライン

let _viewerBlobUrls = [];

function revokeViewerBlobs() {
  for (const url of _viewerBlobUrls) URL.revokeObjectURL(url);
  _viewerBlobUrls = [];
}

async function resolveImages(datasetName, imgIds) {
  revokeViewerBlobs();
  const db = await openDataset(datasetName);
  if (!db) return {};

  const result = {};
  for (const id of imgIds) {
    let stmt;
    try {
      stmt = db.prepare('SELECT data, mime FROM images WHERE id = ?');
      stmt.bind([id]);
      if (stmt.step()) {
        const row = stmt.getAsObject(null);
        if (row['data'] instanceof Uint8Array) {
          const blob = new Blob([row['data']], { type: row['mime'] || 'image/jpeg' });
          const blobUrl = URL.createObjectURL(blob);
          _viewerBlobUrls.push(blobUrl);
          result[id] = blobUrl;
        }
      }
    } catch (e) {
      console.warn('Image resolve error:', id, e);
    } finally {
      if (stmt) stmt.free();
    }
  }
  return result;
}

async function loadPage(dataset, pageId, url, addToHistory) {
  const frame = $('browser-frame');
  frame.srcdoc = '<p style="color:#888;padding:20px;font-family:sans-serif">読み込み中...</p>';

  try {
    const page = await getPage(dataset, pageId);
    if (!page) {
      frame.srcdoc = '<p style="color:#888;padding:20px;font-family:sans-serif">ページが見つかりません</p>';
      return;
    }

    let html = page.html;

    // localnet://img/{id} → BlobURL
    const imgPattern = /localnet:\/\/img\/(\d+)/g;
    const imgIds = new Set();
    let m;
    while ((m = imgPattern.exec(html)) !== null) imgIds.add(parseInt(m[1]));

    if (imgIds.size > 0) {
      const blobUrls = await resolveImages(dataset, Array.from(imgIds));
      for (const [id, blobUrl] of Object.entries(blobUrls)) {
        html = html.replaceAll(`localnet://img/${id}`, blobUrl);
      }
    }

    // 全リンクのhrefを絶対URLに変換してからインターセプト
    // 相対パスが srcdoc 内で壊れるのを防ぐ
    const pageOrigin = new URL(page.url).origin;
    const pageBase = page.url.replace(/[^/]*$/, '');

    // <a href="..."> を絶対URLに変換
    html = html.replace(/<a\s([^>]*?)href=["']([^"']+)["']/gi, (match, pre, href) => {
      if (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('javascript:') || href.startsWith('#') || href.startsWith('mailto:')) {
        return match;
      }
      let absUrl;
      if (href.startsWith('/')) {
        absUrl = pageOrigin + href;
      } else {
        absUrl = pageBase + href;
      }
      return `<a ${pre}href="${absUrl}"`;
    });

    // リンクインターセプト注入
    const interceptScript = `
      <script>
        document.addEventListener('click', function(e) {
          const a = e.target.closest('a');
          if (!a) return;
          e.preventDefault();
          e.stopPropagation();
          var href = a.getAttribute('href');
          if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
            window.parent.postMessage({ type: 'navigate', url: href }, '*');
          }
        }, true);
      </script>
    `;
    html = html.replace('</body>', interceptScript + '</body>');

    frame.srcdoc = html;

    // タブ情報更新
    const tab = currentTab();
    tab.title = page.title || url;
    tab.url = url;
    tab.dataset = dataset;
    tab.pageId = pageId;
    updateNavButtons();

    // 履歴に追加
    if (addToHistory) {
      historyStore.add({ url, title: page.title, dataset, pageId });
    }

    updateBookmarkIcon();

  } catch (e) {
    frame.srcdoc = `<p style="color:#888;padding:20px;font-family:sans-serif">エラー: ${escHtml(e.message)}</p>`;
  }
}

// iframe内リンクナビゲーション
window.addEventListener('message', async (e) => {
  if (!e.data || e.data.type !== 'navigate') return;
  const url = e.data.url;

  // findPageByUrl が内部でURL正規化バリエーションを全部試す
  const found = await findPageByUrl(url);
  if (found) {
    navigateTo(found.dataset, found.id, url, '');
    await loadPage(found.dataset, found.id, url, true);
    return;
  }

  $('browser-frame').srcdoc = `
    <div style="color:#888;padding:20px;font-family:sans-serif">
      <p>このページはローカルにありません</p>
      <p style="font-size:0.85em;margin-top:8px;word-break:break-all">${escHtml(url)}</p>
    </div>
  `;
});
