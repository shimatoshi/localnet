// クロール管理

let crawlTargetUrl = '';
let _currentCrawlJobId = null;

function onCrawlTabOpen() {
  if (isOnline) {
    hide('crawl-offline');
    show('crawl-online');
    loadSites();
    setupImport();
    checkActiveJobs();
  } else {
    show('crawl-offline');
    hide('crawl-online');
  }
}

async function checkActiveJobs() {
  if (_currentCrawlJobId) return;
  try {
    const res = await fetch('/api/jobs/active');
    const jobs = await res.json();
    if (jobs.length > 0) {
      const job = jobs[0];
      _currentCrawlJobId = job.job_id;
      show('progress-section');
      show('btn-stop');
      $('btn-crawl').disabled = true;
      addLog(`実行中のジョブに再接続: ${job.job_id} (${job.domain || ''})`);
      addLog(`現在: ${job.page_count || 0} 件取得済み`);
      listenSSE(job.job_id, () => {
        $('btn-crawl').disabled = false;
        hide('btn-stop');
        _currentCrawlJobId = null;
        loadSites();
      });
      _statusPollTimer = setInterval(async () => {
        if (!_currentCrawlJobId) { clearInterval(_statusPollTimer); return; }
        try {
          const r = await fetch(`/api/jobs/${_currentCrawlJobId}`);
          const j = await r.json();
          if (j.status === 'running') {
            addLog(`\r[${j.page_count || 0} 件取得済み]`);
          } else {
            clearInterval(_statusPollTimer);
          }
        } catch (e) {}
      }, 10000);
    }
  } catch (e) {}
}

let _statusPollTimer = null;

window.selectTarget = function() {
  const url = $('crawl-url').value.trim();
  if (!url) return;
  let normalized = url;
  if (!normalized.startsWith('http')) normalized = 'https://' + normalized;
  crawlTargetUrl = normalized;
  $('crawl-url').value = normalized;
  $('crawl-target').textContent = normalized;
  show('crawl-config');
};

window.doCrawl = async function() {
  const url = crawlTargetUrl || $('crawl-url').value.trim();
  if (!url) return;
  const depth = parseInt($('crawl-depth').value) || 0;
  const delay = parseFloat($('crawl-delay').value) || 1.0;
  const excludeStr = $('crawl-exclude').value.trim();
  const exclude = excludeStr ? excludeStr.split(',').map(s => s.trim()).filter(Boolean) : [];

  $('btn-crawl').disabled = true;
  show('btn-stop');
  clearLog();
  show('progress-section');

  try {
    const res = await fetch('/api/crawl', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, depth, delay, exclude }),
    });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); $('btn-crawl').disabled = false; hide('btn-stop'); return; }
    _currentCrawlJobId = data.job_id;
    addLog(`クロール開始: ${data.job_id} (深さ: ${depth === 0 ? '無制限' : depth})`);
    listenSSE(data.job_id, () => {
      $('btn-crawl').disabled = false;
      hide('btn-stop');
      _currentCrawlJobId = null;
      loadSites();
    });
  } catch (e) {
    addLog('エラー: ' + e.message);
    $('btn-crawl').disabled = false;
    hide('btn-stop');
  }
};

window.stopCrawl = async function() {
  if (!_currentCrawlJobId) return;
  try {
    await fetch(`/api/jobs/${_currentCrawlJobId}/stop`, { method: 'POST' });
    addLog('停止リクエスト送信...');
  } catch (e) {
    addLog('停止エラー: ' + e.message);
  }
};

window.doResume = async function(domain) {
  clearLog();
  show('progress-section');
  show('btn-stop');

  try {
    const res = await fetch(`/api/resume/${encodeURIComponent(domain)}`, { method: 'POST' });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); hide('btn-stop'); return; }
    _currentCrawlJobId = data.job_id;
    addLog(`再開: ${data.job_id} (${domain})`);
    listenSSE(data.job_id, () => {
      hide('btn-stop');
      _currentCrawlJobId = null;
      loadSites();
    });
  } catch (e) {
    addLog('エラー: ' + e.message);
    hide('btn-stop');
  }
};

async function loadSites() {
  try {
    const res = await fetch('/api/sites');
    renderSites(await res.json());
  } catch (e) {
    $('sites-list').innerHTML = '<p class="muted">取得エラー</p>';
  }
}

function renderSites(sites) {
  const list = $('sites-list');
  if (sites.length === 0) { list.innerHTML = '<p class="muted">なし</p>'; return; }
  list.innerHTML = '';
  sites.forEach(site => {
    const item = document.createElement('div');
    item.className = 'site-item';
    let actions = `<button class="btn-resume" data-domain="${escHtml(site.domain)}">再開</button>`;
    if (site.has_catalog) {
      actions += `<button class="btn-downloaded" disabled>&#10003; ${site.page_count} ページ</button>`;
      actions += `<button class="btn-build" data-domain="${escHtml(site.domain)}">再生成</button>`;
    } else {
      actions += `<button class="btn-build" data-domain="${escHtml(site.domain)}">カタログ生成</button>`;
    }
    actions += `<button class="btn-export" data-domain="${escHtml(site.domain)}">エクスポート</button>`;
    item.innerHTML = `
      <div class="site-domain">${escHtml(site.domain)}</div>
      <div class="site-stats">${site.file_count} ファイル</div>
      <div class="site-actions">${actions}</div>
    `;
    list.appendChild(item);
    item.querySelector('.btn-resume').addEventListener('click', function() { doResume(this.dataset.domain); });
    item.querySelectorAll('.btn-build').forEach(btn => {
      btn.addEventListener('click', function() { doBuild(this.dataset.domain); });
    });
    item.querySelector('.btn-export').addEventListener('click', function() {
      exportSite(this.dataset.domain, this);
    });
  });
}

async function doBuild(domain) {
  clearLog();
  show('progress-section');
  try {
    const res = await fetch(`/api/build/${encodeURIComponent(domain)}`, { method: 'POST' });
    const data = await res.json();
    if (data.error) { addLog('エラー: ' + data.error); return; }
    addLog(`カタログ生成: ${data.job_id}`);
    listenSSE(data.job_id, () => { loadSites(); });
  } catch (e) {
    addLog('エラー: ' + e.message);
  }
}

async function exportSite(domain, btn) {
  btn.disabled = true;
  btn.textContent = 'エクスポート中...';
  try {
    const res = await fetch(`/api/export/${encodeURIComponent(domain)}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${domain}.tar.gz`;
    a.style.display = 'none';
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(url); a.remove(); }, 1000);
    btn.textContent = 'エクスポート';
    btn.disabled = false;
  } catch (e) {
    btn.textContent = 'エクスポート';
    btn.disabled = false;
    alert('エクスポートエラー: ' + e.message);
  }
}

function setupImport() {
  const fileInput = $('import-file');
  const statusEl = $('import-status');
  if (!fileInput || fileInput._bound) return;
  fileInput._bound = true;

  fileInput.addEventListener('change', async function() {
    const file = this.files[0];
    if (!file) return;

    statusEl.classList.remove('hidden');
    statusEl.innerHTML = `<p class="muted">アップロード中: ${escHtml(file.name)}...</p>`;

    try {
      const formData = new FormData();
      formData.append('file', file);

      const res = await fetch('/api/import', { method: 'POST', body: formData });
      const data = await res.json();

      if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

      statusEl.innerHTML = `<p class="muted">カタログ生成中: ${escHtml(data.domain || '...')} (job: ${data.job_id})</p>`;

      await watchImportJob(data.job_id, statusEl);
    } catch (e) {
      statusEl.innerHTML = `<p style="color:var(--err)">エラー: ${escHtml(e.message)}</p>`;
    }

    fileInput.value = '';
  });
}

async function watchImportJob(jobId, statusEl) {
  try {
    const evtSource = new EventSource(`/api/jobs/${jobId}/stream`);
    await new Promise((resolve, reject) => {
      evtSource.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === 'log') {
          statusEl.innerHTML = `<p class="muted">${escHtml(msg.message)}</p>`;
        } else if (msg.type === 'done') {
          evtSource.close();
          statusEl.innerHTML = '<p style="color:var(--ok)">インポート完了</p>';
          loadSites();
          resolve();
        } else if (msg.type === 'error') {
          evtSource.close();
          statusEl.innerHTML = `<p style="color:var(--err)">エラー: ${escHtml(msg.message)}</p>`;
          reject(new Error(msg.message));
        }
      };
      evtSource.onerror = () => {
        evtSource.close();
        statusEl.innerHTML = '<p style="color:var(--err)">接続エラー</p>';
        reject(new Error('SSE connection error'));
      };
    });
  } catch (e) {}
}

document.addEventListener('DOMContentLoaded', () => {
  $('crawl-url').addEventListener('keydown', e => { if (e.key === 'Enter') selectTarget(); });
});
