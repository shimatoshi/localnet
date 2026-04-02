// Localnet — ユーティリティ + 画面管理 + 初期化

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

function showScreen(id) {
  document.querySelectorAll('.screen').forEach(s => s.classList.add('hidden'));
  $(id).classList.remove('hidden');
  hideMenu();

  const nav = $('main-nav');
  if (id === 'screen-browser') {
    nav.classList.add('hidden');
  } else {
    nav.classList.remove('hidden');
  }

  const navMap = {
    'screen-home': 'search', 'screen-results': 'search',
    'screen-data': 'data',
    'screen-crawl': 'crawl',
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

  document.addEventListener('click', (e) => {
    if (!e.target.closest('#browser-menu') && !e.target.closest('.bar-btn')) hideMenu();
  });
});
