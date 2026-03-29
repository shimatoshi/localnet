// Localnet — メインコントローラー

function $(id) { return document.getElementById(id); }
function show(id) { $(id).classList.remove('hidden'); }
function hide(id) { $(id).classList.add('hidden'); }

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function formatSize(bytes) {
  if (!bytes) return '0 B';
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
  return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
}

// ========== 画面管理 ==========

let _prevScreen = 'screen-home';

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  $(id).classList.remove('hidden');
  hideMenu();

  // ブラウザ画面ではメインナビ非表示（ブラウザバーがある）
  const nav = $('main-nav');
  if (id === 'screen-browser') {
    nav.classList.add('hidden');
  } else {
    nav.classList.remove('hidden');
  }

  // ナビのアクティブ状態
  const navMap = {
    'screen-home': 'search', 'screen-results': 'search',
    'screen-data': 'data', 'screen-crawl': 'crawl',
    'screen-history': 'history', 'screen-bookmarks': 'bookmarks',
  };
  document.querySelectorAll('#main-nav button').forEach(b => {
    b.classList.toggle('active', b.dataset.nav === navMap[id]);
  });

  if (id === 'screen-data') onDataTabOpen();
  if (id === 'screen-crawl') onCrawlTabOpen();
  if (id === 'screen-history') renderHistory();
  if (id === 'screen-bookmarks') renderBookmarks();
  if (id === 'screen-tabs') renderTabs();
}

window.goHome = function() {
  showScreen('screen-home');
  $('home-search').value = '';
  $('home-search').focus();
  loadHomeShortcuts();
};

window.closeSubScreen = function() {
  goHome();
};

// ========== タブ管理 ==========

let tabs = []; // { id, title, url, dataset, pageId, historyStack, historyPos }
let activeTabIndex = 0;
let _tabIdCounter = 0;

function createTab() {
  const tab = {
    id: ++_tabIdCounter,
    title: '新しいタブ',
    url: '',
    dataset: '',
    pageId: 0,
    historyStack: [],
    historyPos: -1,
  };
  tabs.push(tab);
  activeTabIndex = tabs.length - 1;
  updateTabCount();
  return tab;
}

function updateTabCount() {
  $('tab-count').textContent = tabs.length || 1;
}

window.addNewTab = function() {
  createTab();
  goHome();
};

window.showTabs = function() {
  showScreen('screen-tabs');
};

function renderTabs() {
  const el = $('tabs-list');
  if (tabs.length === 0) {
    el.innerHTML = '<p class="muted" style="padding:40px 16px;text-align:center">タブなし</p>';
    return;
  }
  el.innerHTML = '';
  tabs.forEach((tab, i) => {
    const card = document.createElement('div');
    card.className = 'tab-card' + (i === activeTabIndex ? ' active-tab' : '');
    card.innerHTML = `
      <div class="tab-title">${escHtml(tab.title || '新しいタブ')}</div>
      <button class="tab-close" data-idx="${i}">&times;</button>
    `;
    card.addEventListener('click', (e) => {
      if (e.target.classList.contains('tab-close')) return;
      activeTabIndex = i;
      if (tab.url) {
        showScreen('screen-browser');
        restoreTab(tab);
      } else {
        goHome();
      }
    });
    card.querySelector('.tab-close').addEventListener('click', () => {
      tabs.splice(i, 1);
      if (tabs.length === 0) {
        activeTabIndex = 0;
        goHome();
      } else {
        activeTabIndex = Math.min(activeTabIndex, tabs.length - 1);
        renderTabs();
      }
      updateTabCount();
    });
    el.appendChild(card);
  });
}

function currentTab() {
  if (tabs.length === 0) createTab();
  return tabs[activeTabIndex];
}

// ========== ナビゲーション（戻る/進む） ==========

function navigateTo(dataset, pageId, url, title) {
  const tab = currentTab();
  // 現在位置より先を切り捨て
  tab.historyStack = tab.historyStack.slice(0, tab.historyPos + 1);
  tab.historyStack.push({ dataset, pageId, url, title });
  tab.historyPos = tab.historyStack.length - 1;
  tab.url = url;
  tab.title = title || url;
  tab.dataset = dataset;
  tab.pageId = pageId;
  updateNavButtons();
}

function updateNavButtons() {
  const tab = currentTab();
  $('btn-back').disabled = tab.historyPos <= 0;
  $('btn-forward').disabled = tab.historyPos >= tab.historyStack.length - 1;
}

window.browserBack = function() {
  const tab = currentTab();
  if (tab.historyPos > 0) {
    tab.historyPos--;
    const entry = tab.historyStack[tab.historyPos];
    tab.url = entry.url;
    tab.title = entry.title;
    tab.dataset = entry.dataset;
    tab.pageId = entry.pageId;
    loadPage(entry.dataset, entry.pageId, entry.url, false);
  }
};

window.browserForward = function() {
  const tab = currentTab();
  if (tab.historyPos < tab.historyStack.length - 1) {
    tab.historyPos++;
    const entry = tab.historyStack[tab.historyPos];
    tab.url = entry.url;
    tab.title = entry.title;
    tab.dataset = entry.dataset;
    tab.pageId = entry.pageId;
    loadPage(entry.dataset, entry.pageId, entry.url, false);
  }
};

function restoreTab(tab) {
  if (tab.historyPos >= 0) {
    const entry = tab.historyStack[tab.historyPos];
    loadPage(entry.dataset, entry.pageId, entry.url, false);
  }
}

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
    await bookmarkStore.add({ url: tab.url, title: tab.title, dataset: tab.dataset, pageId: tab.pageId });
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
    div.addEventListener('click', () => {
      openInBrowser(h.dataset, h.pageId, h.url);
    });
    el.appendChild(div);
  });
}

window.clearHistory = async function() {
  if (!confirm('履歴を消去しますか？')) return;
  await historyStore.clear();
  renderHistory();
};

// ========== ブックマーク ==========

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
    div.addEventListener('click', () => {
      openInBrowser(b.dataset, b.pageId, b.url);
    });
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
    items.push({ title: b.title, url: b.url, dataset: b.dataset, pageId: b.pageId, icon: '&#9733;' });
  }
  for (const h of recent) {
    if (seen.has(h.url) || items.length >= 8) break;
    seen.add(h.url);
    items.push({ title: h.title, url: h.url, dataset: h.dataset, pageId: h.pageId, icon: '&#9201;' });
  }

  el.innerHTML = '';
  items.forEach(item => {
    const chip = document.createElement('button');
    chip.className = 'shortcut-chip';
    chip.innerHTML = `<span>${item.icon}</span> ${escHtml(item.title || item.url).slice(0, 24)}`;
    chip.addEventListener('click', () => openInBrowser(item.dataset, item.pageId, item.url));
    el.appendChild(chip);
  });
}

// ========== ブラウザで開く共通 ==========

window.openInBrowser = async function(dataset, pageId, url) {
  if (!dataset || !pageId) {
    const found = await findPageByUrl(url);
    if (found) { dataset = found.dataset; pageId = found.id; }
    else { return; }
  }
  navigateTo(dataset, pageId, url, '');
  showScreen('screen-browser');
  await loadPage(dataset, pageId, url, true);
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
          openInBrowser(h.dataset, h.pageId, h.url);
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

// ========== SSE ==========

let currentEventSource = null;

function listenSSE(jobId, onFinish) {
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  currentEventSource = es;
  es.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    if (msg.type === 'ping') return;
    if (msg.type === 'log') addLog(msg.message);
    if (msg.type === 'done') { es.close(); currentEventSource = null; addLog('--- 完了 ---'); if (onFinish) onFinish(); }
    if (msg.type === 'error') { es.close(); currentEventSource = null; addLog('エラー: ' + msg.message); if (onFinish) onFinish(); }
  };
  es.onerror = () => { es.close(); currentEventSource = null; addLog('接続が切断されました'); if (onFinish) onFinish(); };
}

function addLog(msg) {
  const area = $('log-area');
  if (!area) return;
  if (msg.startsWith('\r')) {
    msg = msg.slice(1);
    const last = area.lastElementChild;
    if (last && last.classList.contains('log-progress')) { last.textContent = msg; area.scrollTop = area.scrollHeight; return; }
    const line = document.createElement('div');
    line.className = 'log-line log-progress';
    line.textContent = msg;
    area.appendChild(line);
    area.scrollTop = area.scrollHeight;
    return;
  }
  const line = document.createElement('div');
  line.className = 'log-line';
  line.textContent = msg;
  area.appendChild(line);
  area.scrollTop = area.scrollHeight;
}

function clearLog() { const area = $('log-area'); if (area) area.innerHTML = ''; }

// ========== Online ==========

let isOnline = navigator.onLine;
window.addEventListener('online', () => { isOnline = true; });
window.addEventListener('offline', () => { isOnline = false; });

// ========== Service Worker + Persistence ==========

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}

async function requestPersistence() {
  if (navigator.storage && navigator.storage.persist) {
    await navigator.storage.persist();
  }
}

// ========== Init ==========

document.addEventListener('DOMContentLoaded', () => {
  requestPersistence();
  createTab();
  loadHomeShortcuts();

  // sql.js を先行ロード → データセットも先行オープン
  initSQL().then(async () => {
    const datasets = await dbStore.listMeta();
    for (const ds of datasets) {
      openDataset(ds.name).catch(() => {});
    }
  }).catch(() => {});

  // ホーム検索
  $('home-search').addEventListener('keydown', e => {
    if (e.key === 'Enter') { $('home-suggest').classList.add('hidden'); doSearch($('home-search').value.trim()); }
  });
  // 結果画面検索
  $('results-search').addEventListener('keydown', e => {
    if (e.key === 'Enter') { $('results-suggest').classList.add('hidden'); doSearch($('results-search').value.trim()); }
  });

  setupSuggest('home-search', 'home-suggest');
  setupSuggest('results-search', 'results-suggest');

  // ブラウザ外タップでメニュー閉じ
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#browser-menu') && !e.target.closest('.bar-btn')) hideMenu();
  });
});
