// SSE接続 + ログ表示

let currentEventSource = null;
let _sseReconnectTimer = null;

function listenSSE(jobId, onFinish) {
  if (currentEventSource) { currentEventSource.close(); currentEventSource = null; }
  clearTimeout(_sseReconnectTimer);

  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  currentEventSource = es;

  es.onmessage = (event) => {
    let msg;
    try { msg = JSON.parse(event.data); } catch { return; }
    if (msg.type === 'ping') return;
    if (msg.type === 'log') addLog(msg.message);
    if (msg.type === 'done') {
      es.close(); currentEventSource = null;
      addLog('--- 完了 ---');
      if (onFinish) onFinish();
    }
    if (msg.type === 'error') {
      es.close(); currentEventSource = null;
      addLog('エラー: ' + msg.message);
      if (onFinish) onFinish();
    }
  };

  es.onerror = () => {
    es.close();
    currentEventSource = null;
    addLog('接続が切断されました。再接続中...');
    _sseReconnectTimer = setTimeout(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        const job = await res.json();
        if (job.status === 'running') {
          addLog('再接続...');
          listenSSE(jobId, onFinish);
        } else if (job.status === 'done') {
          addLog('--- 完了 ---');
          if (onFinish) onFinish();
        } else if (job.status === 'error') {
          addLog('エラー: ' + (job.error || '不明'));
          if (onFinish) onFinish();
        }
      } catch (e) {
        addLog('サーバーに接続できません。後で再試行...');
        _sseReconnectTimer = setTimeout(() => listenSSE(jobId, onFinish), 10000);
      }
    }, 3000);
  };
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
