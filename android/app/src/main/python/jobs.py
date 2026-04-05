"""ジョブ管理 — バックグラウンドタスク実行"""

import os
import sys
import json
import threading
import queue
import uuid
import time
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import CACHE_BASE
from catalog_builder import build_catalog

# 完了ジョブの保持期間（秒）
_JOB_TTL = 3600


class Job:
    def __init__(self):
        self.id = str(uuid.uuid4())[:8]
        self.status = 'pending'
        self.log_queue = queue.Queue(maxsize=1000)
        self.error = None
        self.domain = None
        self._crawler = None
        self._stop_requested = threading.Event()
        self._finished_at = None

    def log(self, message):
        item = {"type": "log", "message": str(message)}
        while self.log_queue.full():
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        try:
            self.log_queue.put_nowait(item)
        except queue.Full:
            pass

    def finish(self, **extra):
        self.status = 'done'
        self._finished_at = time.time()
        self.log_queue.put({"type": "done", "domain": self.domain, **extra})

    def fail(self, error):
        self.status = 'error'
        self._finished_at = time.time()
        self.error = str(error)
        self.log_queue.put({"type": "error", "message": self.error})

    def to_dict(self):
        d = {
            'job_id': self.id,
            'status': self.status,
            'domain': self.domain,
            'error': self.error,
            'page_count': 0,
        }
        if self._crawler:
            d['page_count'] = self._crawler.page_count
        return d


# グローバルジョブストア
_jobs = {}
_jobs_lock = threading.Lock()


def _purge_old_jobs():
    """TTLを超えた完了ジョブを削除（ロック内で呼ぶこと）"""
    now = time.time()
    expired = [
        jid for jid, j in _jobs.items()
        if j._finished_at and now - j._finished_at > _JOB_TTL
    ]
    for jid in expired:
        del _jobs[jid]


def get_job(job_id):
    with _jobs_lock:
        return _jobs.get(job_id)


def stop_job(job_id):
    job = get_job(job_id)
    if not job:
        return False
    job._stop_requested.set()
    if job._crawler:
        job._crawler.stop()
    return job.status in ('running', 'pending')


def _start_job(target, *args):
    job = Job()
    with _jobs_lock:
        _purge_old_jobs()
        _jobs[job.id] = job
    threading.Thread(target=target, args=(job, *args), daemon=True).start()
    return job


# === ジョブ実行関数 ===

def _run_crawl(job, url, depth, delay, exclude):
    """クロールジョブ（APK版では未実装 — サーバー経由で実行）"""
    job.status = 'running'
    job.domain = urlparse(url).netloc
    job.fail(NotImplementedError("アプリ内クロールは実装予定です。サーバー経由でクロールしてください。"))


def _run_resume(job, domain):
    job.status = 'running'
    job.domain = domain
    job.fail(NotImplementedError("アプリ内クロールは実装予定です。サーバー経由でクロールしてください。"))


def _run_recrawl(job, domain):
    job.status = 'running'
    job.domain = domain
    job.fail(NotImplementedError("アプリ内クロールは実装予定です。サーバー経由でクロールしてください。"))


def _run_build(job, domain):
    """カタログ生成ジョブ"""
    job.status = 'running'
    job.domain = domain
    try:
        build_catalog(domain, log=job.log)
        job.finish()
    except Exception as e:
        job.fail(e)


def _run_import(job, domain):
    """アーカイブからインポート → カタログ生成"""
    job.status = 'running'
    job.domain = domain
    try:
        cache_dir = os.path.join(CACHE_BASE, domain)
        if not os.path.isdir(cache_dir):
            raise FileNotFoundError(f'キャッシュなし: {domain}')

        job.log(f"インポート: {domain}")
        job.log("--- カタログ生成中 ---")
        build_catalog(domain, log=job.log)
        job.finish()
    except Exception as e:
        job.fail(e)


# === 公開API ===

def start_crawl_job(url, depth, delay, exclude):
    return _start_job(_run_crawl, url, depth, delay, exclude)


def start_resume_job(domain):
    return _start_job(_run_resume, domain)


def start_build_job(domain):
    return _start_job(_run_build, domain)


def start_recrawl_job(domain):
    return _start_job(_run_recrawl, domain)


def start_import_job(domain):
    return _start_job(_run_import, domain)


def get_active_jobs():
    """実行中のジョブ一覧を返す"""
    with _jobs_lock:
        return [j.to_dict() for j in _jobs.values() if j.status == 'running']


def get_all_sites():
    sites = []
    if not os.path.exists(CACHE_BASE):
        return sites
    for name in sorted(os.listdir(CACHE_BASE)):
        site_dir = os.path.join(CACHE_BASE, name)
        if not os.path.isdir(site_dir):
            continue
        file_count = sum(1 for _, _, files in os.walk(site_dir) for f in files)
        catalog_path = os.path.join(site_dir, 'catalog.json')
        has_catalog = os.path.exists(catalog_path)
        page_count = 0
        if has_catalog:
            try:
                with open(catalog_path, 'r') as f:
                    page_count = len(json.load(f))
            except Exception:
                pass
        sites.append({
            "domain": name,
            "file_count": file_count,
            "has_catalog": has_catalog,
            "page_count": page_count,
        })
    return sites
