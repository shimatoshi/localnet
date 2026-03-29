"""ジョブ管理 — バックグラウンドタスク実行"""

import os
import sys
import threading
import queue
import uuid
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import CACHE_BASE, DATASETS_DIR
from crawler import WgetCrawler
from dataset_builder import DatasetBuilder


class Job:
    def __init__(self):
        self.id = str(uuid.uuid4())[:8]
        self.status = 'pending'
        self.log_queue = queue.Queue(maxsize=1000)
        self.error = None
        self.domain = None
        self.dataset_file = None

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
        if 'dataset_file' in extra:
            self.dataset_file = extra['dataset_file']
        self.log_queue.put({"type": "done", "domain": self.domain, **extra})

    def fail(self, error):
        self.status = 'error'
        self.error = str(error)
        self.log_queue.put({"type": "error", "message": self.error})

    def to_dict(self):
        return {
            'job_id': self.id,
            'status': self.status,
            'domain': self.domain,
            'error': self.error,
            'dataset_file': self.dataset_file,
        }


# グローバルジョブストア
_jobs = {}
_jobs_lock = threading.Lock()


def get_job(job_id):
    with _jobs_lock:
        return _jobs.get(job_id)


def _start_job(target, *args):
    job = Job()
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=target, args=(job, *args), daemon=True).start()
    return job


# === ジョブ実行関数 ===

def _run_crawl(job, url, depth, delay, daily_limit, exclude, auto_build=False):
    job.status = 'running'
    job.domain = urlparse(url).netloc
    try:
        crawler = WgetCrawler(
            url, max_depth=depth, delay=delay, daily_limit=daily_limit,
            log=job.log, exclude=exclude,
        )
        job.domain = crawler.domain
        crawler.run()

        if auto_build:
            job.log("--- クロール完了、データセット構築を開始 ---")
            builder = DatasetBuilder(crawler.domain, log=job.log)
            output = builder.build()
            job.finish(dataset_file=os.path.basename(output))
        else:
            job.finish()
    except Exception as e:
        job.fail(e)


def _run_build(job, domain):
    job.status = 'running'
    job.domain = domain
    try:
        builder = DatasetBuilder(domain, log=job.log)
        output = builder.build()
        job.finish(dataset_file=os.path.basename(output))
    except Exception as e:
        job.fail(e)


# === 公開API ===

def start_crawl_job(url, depth, delay, daily_limit, exclude, auto_build=False):
    return _start_job(_run_crawl, url, depth, delay, daily_limit, exclude, auto_build)


def start_build_job(domain):
    return _start_job(_run_build, domain)


def get_all_sites():
    """cache/ 内の全ドメインディレクトリを列挙"""
    sites = []
    if not os.path.exists(CACHE_BASE):
        return sites
    for name in sorted(os.listdir(CACHE_BASE)):
        site_dir = os.path.join(CACHE_BASE, name)
        if not os.path.isdir(site_dir):
            continue
        # ファイル数カウント
        file_count = sum(1 for _, _, files in os.walk(site_dir) for f in files)
        # データセット存在チェック
        dataset_path = os.path.join(DATASETS_DIR, f"{name}.sqlite")
        dataset_size = os.path.getsize(dataset_path) if os.path.exists(dataset_path) else None
        sites.append({
            "domain": name,
            "file_count": file_count,
            "has_dataset": dataset_size is not None,
            "dataset_size": dataset_size,
        })
    return sites


def get_all_datasets():
    """datasets/ 内の全データセットを列挙"""
    datasets = []
    os.makedirs(DATASETS_DIR, exist_ok=True)
    for f in sorted(os.listdir(DATASETS_DIR)):
        if not f.endswith('.sqlite'):
            continue
        path = os.path.join(DATASETS_DIR, f)
        size = os.path.getsize(path)

        # メタデータ取得
        import sqlite3
        meta = {}
        try:
            conn = sqlite3.connect(path)
            for row in conn.execute("SELECT key, value FROM meta"):
                meta[row[0]] = row[1]
            conn.close()
        except Exception:
            pass

        datasets.append({
            "name": meta.get("name", f.replace(".sqlite", "")),
            "filename": f,
            "size": size,
            "page_count": int(meta.get("page_count", 0)),
            "created_at": meta.get("created_at", ""),
            "source_url": meta.get("source_url", ""),
        })
    return datasets
