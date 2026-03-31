// ブラウザビュアー — キャッシュAPI経由でHTML表示

function urlToCachePath(url) {
  try {
    const u = new URL(url);
    return { domain: u.hostname, path: u.pathname.replace(/^\//, '') };
  } catch (e) {
    return null;
  }
}

function extractTitleFromHtml(html) {
  const m = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  if (m) return m[1].replace(/<[^>]+>/g, '').trim();
  return '';
}

async function loadPage(url, addToHistory) {
  const frame = $('browser-frame');
  frame.srcdoc = '<p style="color:#888;padding:20px;font-family:sans-serif">読み込み中...</p>';

  const info = urlToCachePath(url);
  if (!info) {
    frame.srcdoc = '<p style="color:#888;padding:20px;font-family:sans-serif">不正なURLです</p>';
    return;
  }

  try {
    const res = await fetch(`/api/cache/${info.domain}/${info.path}`);
    if (!res.ok) {
      frame.srcdoc = `<div style="color:#888;padding:20px;font-family:sans-serif">
        <p>このページはローカルにありません</p>
        <p style="font-size:0.85em;margin-top:8px;word-break:break-all">${escHtml(url)}</p>
      </div>`;
      return;
    }

    let html = await res.text();
    const title = extractTitleFromHtml(html) || url;

    // <base>タグで相対URLを解決
    const baseDir = info.path.replace(/[^/]*$/, '');
    const baseTag = `<base href="/api/cache/${info.domain}/${baseDir}">`;
    if (/<head/i.test(html)) {
      html = html.replace(/<head([^>]*)>/i, `<head$1>${baseTag}`);
    } else {
      html = baseTag + html;
    }

    // リンクインターセプト注入
    const domain = info.domain;
    const interceptScript = `
      <script>
        document.addEventListener('click', function(e) {
          var a = e.target.closest('a');
          if (!a) return;
          e.preventDefault();
          e.stopPropagation();
          var href = a.href;
          if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;

          // /api/cache/domain/path → https://domain/path に変換
          var m = href.match(/\\/api\\/cache\\/([^\\/]+)\\/(.*)/);
          if (m) {
            window.parent.postMessage({ type: 'navigate', url: 'https://' + m[1] + '/' + m[2] }, '*');
          } else if (href.startsWith('http')) {
            window.parent.postMessage({ type: 'navigate', url: href }, '*');
          }
        }, true);
      </script>
    `;
    if (html.includes('</body>')) {
      html = html.replace('</body>', interceptScript + '</body>');
    } else {
      html += interceptScript;
    }

    frame.srcdoc = html;

    // タブ情報更新
    const tab = currentTab();
    tab.title = title;
    tab.url = url;
    updateNavButtons();

    if (addToHistory) {
      historyStore.add({ url, title });
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
  openInBrowser(url);
});
