// Localnet — メインアプリコントローラー

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

// ========== Tab switching ==========

let currentTab = 'tab-search';

window.switchTab = function(tabId) {
  // ビュアーは特殊（ナビから切り替えない）
  if (tabId !== 'tab-viewer') currentTab = tabId;

  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  $(tabId).classList.remove('hidden');
  document.querySelectorAll('.nav-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tabId);
  });

  if (tabId === 'tab-search') onSearchTabOpen();
  if (tabId === 'tab-data') onDataTabOpen();
  if (tabId === 'tab-crawl') onCrawlTabOpen();
};

// ========== Service Worker ==========

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/static/sw.js').catch(() => {});
}

// ========== Storage Persistence ==========

async function requestPersistence() {
  if (navigator.storage && navigator.storage.persist) {
    const granted = await navigator.storage.persist();
    if (granted) {
      console.log('Storage persistence granted');
    }
  }
}

// ========== Online/Offline ==========

let isOnline = navigator.onLine;

function updateOnlineStatus() {
  isOnline = navigator.onLine;
  if (currentTab === 'tab-crawl') onCrawlTabOpen();
  if (currentTab === 'tab-data') onDataTabOpen();
}

window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);

// ========== SSE ==========

let currentEventSource = null;

function listenSSE(jobId, onFinish) {
  if (currentEventSource) {
    currentEventSource.close();
    currentEventSource = null;
  }
  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  currentEventSource = es;
  es.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    if (msg.type === 'ping') return;
    if (msg.type === 'log') addLog(msg.message);
    if (msg.type === 'done') {
      es.close();
      currentEventSource = null;
      addLog('--- 完了 ---');
      if (onFinish) onFinish();
    }
    if (msg.type === 'error') {
      es.close();
      currentEventSource = null;
      addLog('エラー: ' + msg.message);
      if (onFinish) onFinish();
    }
  };
  es.onerror = () => {
    es.close();
    currentEventSource = null;
    addLog('接続が切断されました');
    if (onFinish) onFinish();
  };
}

// ========== Log ==========

function addLog(msg) {
  const area = $('log-area');
  if (!area) return;
  if (msg.startsWith('\r')) {
    msg = msg.slice(1);
    const last = area.lastElementChild;
    if (last && last.classList.contains('log-progress')) {
      last.textContent = msg;
      area.scrollTop = area.scrollHeight;
      return;
    }
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

function clearLog() {
  const area = $('log-area');
  if (area) area.innerHTML = '';
}

// ========== Init ==========

document.addEventListener('DOMContentLoaded', () => {
  requestPersistence();
  $('search-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') doSearch();
  });
});
