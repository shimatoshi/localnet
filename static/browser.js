// ブラウジングUI — メニュー・ブクマ・履歴・ショートカット・サジェスト・ページ表示

// ========== ブラウザメニュー ==========

window.toggleMenu = function() {
  $('browser-menu').classList.toggle('hidden');
};

function hideMenu() {
  $('browser-menu').classList.add('hidden');
}

window.toggleBookmark = async function() {
  hideMenu();
  const tab = currentTab();
  if (!tab.url) return;
  const has = await bookmarkStore.has(tab.url);
  if (has) {
    await bookmarkStore.remove(tab.url);
  } else {
    await bookmarkStore.add({ url: tab.url, title: tab.title });
  }
  updateBookmarkIcon();
};

async function updateBookmarkIcon() {
  const tab = currentTab();
  const has = tab.url ? await bookmarkStore.has(tab.url) : false;
  $('menu-bm-icon').innerHTML = has ? '&#9733;' : '&#9734;';
}

window.sharePage = function() {
  hideMenu();
  const tab = currentTab();
  if (!tab.url) return;
  if (navigator.share) {
    navigator.share({ title: tab.title, url: tab.url }).catch(() => {});
  } else {
    navigator.clipboard.writeText(tab.url).then(() => alert('URLをコピーしました'));
  }
};

// ========== 履歴 ==========

async function renderHistory() {
  const el = $('history-list');
  const items = await historyStore.list(200);
  if (items.length === 0) {
    el.innerHTML = '<p class="muted" style="padding:40px 16px;text-align:center">履歴なし</p>';
    return;
  }
  el.innerHTML = '';
  items.forEach(h => {
    const div = document.createElement('div');
    div.className = 'history-item';
    const d = new Date(h.timestamp);
    div.innerHTML = `
      <div class="history-title">${escHtml(h.title || h.url)}</div>
      <div class="history-url">${escHtml(h.url)}</div>
      <div class="history-time">${d.toLocaleDateString()} ${d.toLocaleTimeString()}</div>
    `;
    div.addEventListener('click', () => openInBrowser(h.url));
    el.appendChild(div);
  });
}

window.clearHistory = async function() {
  if (!confirm('履歴を消去しますか？')) return;
  await historyStore.clear();
  renderHistory();
};

// ========== ブックマーク一覧 ==========

async function renderBookmarks() {
  const el = $('bookmarks-list');
  const items = await bookmarkStore.list();
  if (items.length === 0) {
    el.innerHTML = '<p class="muted" style="padding:40px 16px;text-align:center">ブックマークなし</p>';
    return;
  }
  el.innerHTML = '';
  items.forEach(b => {
    const div = document.createElement('div');
    div.className = 'bookmark-item';
    div.innerHTML = `
      <div class="bookmark-title">${escHtml(b.title || b.url)}</div>
      <div class="bookmark-url">${escHtml(b.url)}</div>
    `;
    div.addEventListener('click', () => openInBrowser(b.url));
    el.appendChild(div);
  });
}

// ========== ホームショートカット ==========

async function loadHomeShortcuts() {
  const el = $('home-shortcuts');
  const bookmarks = await bookmarkStore.list();
  const recent = await historyStore.list(8);

  const items = [];
  const seen = new Set();
  for (const b of bookmarks.slice(0, 4)) {
    if (seen.has(b.url)) continue;
    seen.add(b.url);
    items.push({ title: b.title, url: b.url, icon: '&#9733;' });
  }
  for (const h of recent) {
    if (seen.has(h.url) || items.length >= 8) break;
    seen.add(h.url);
    items.push({ title: h.title, url: h.url, icon: '&#9201;' });
  }

  el.innerHTML = '';
  items.forEach(item => {
    const chip = document.createElement('button');
    chip.className = 'shortcut-chip';
    chip.innerHTML = `<span>${item.icon}</span> ${escHtml(item.title || item.url).slice(0, 24)}`;
    chip.addEventListener('click', () => openInBrowser(item.url));
    el.appendChild(chip);
  });
}

// ========== ブラウザで開く ==========

window.openInBrowser = async function(url) {
  if (!url) return;
  navigateTo(url, '');
  showScreen('screen-browser');
  await loadPage(url, true);
  updateBookmarkIcon();
};

// ========== サジェスト ==========

let _suggestTimer = null;

function setupSuggest(inputId, dropdownId) {
  const input = $(inputId);
  const dd = $(dropdownId);

  input.addEventListener('input', () => {
    clearTimeout(_suggestTimer);
    const q = input.value.trim();
    if (q.length < 2) { dd.classList.add('hidden'); return; }
    _suggestTimer = setTimeout(async () => {
      const histItems = await historyStore.searchTitles(q, 5);
      if (histItems.length === 0) { dd.classList.add('hidden'); return; }
      dd.innerHTML = '';
      histItems.forEach(h => {
        const div = document.createElement('div');
        div.className = 'suggest-item';
        div.innerHTML = `
          <span class="suggest-icon">&#9201;</span>
          <div class="suggest-text">
            <span class="suggest-title">${escHtml(h.title || h.url)}</span>
            <span class="suggest-url">${escHtml(h.url)}</span>
          </div>
        `;
        div.addEventListener('click', () => {
          input.value = h.title || h.url;
          dd.classList.add('hidden');
          openInBrowser(h.url);
        });
        dd.appendChild(div);
      });
      dd.classList.remove('hidden');
    }, 200);
  });

  input.addEventListener('blur', () => {
    setTimeout(() => dd.classList.add('hidden'), 200);
  });

  input.addEventListener('focus', () => {
    if (input.value.trim().length >= 2) input.dispatchEvent(new Event('input'));
  });
}

// ========== ページ表示（旧viewer.js） ==========

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

    // Content-Typeからcharsetを取得し正しくデコード
    const ct = res.headers.get('Content-Type') || '';
    const charsetMatch = ct.match(/charset=([a-zA-Z0-9_-]+)/i);
    const charset = charsetMatch ? charsetMatch[1] : 'utf-8';
    const buf = await res.arrayBuffer();
    let html = new TextDecoder(charset, { fatal: false }).decode(buf);
    const title = extractTitleFromHtml(html) || url;

    // 絶対パス(/で始まるsrc, href)を/api/cache/domain/に書き換え
    const cachePrefix = `/api/cache/${info.domain}`;
    html = html.replace(
      /((?:src|href|action)\s*=\s*["'])\/(?!\/)/gi,
      `$1${cachePrefix}/`
    );

    // <base>タグで相対URLを解決
    const baseDir = info.path.replace(/[^/]*$/, '');
    const baseTag = `<base href="${cachePrefix}/${baseDir}">`;
    if (/<head/i.test(html)) {
      html = html.replace(/<head([^>]*)>/i, `<head$1>${baseTag}`);
    } else {
      html = baseTag + html;
    }

    // リンクインターセプト注入
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
  openInBrowser(e.data.url);
});
