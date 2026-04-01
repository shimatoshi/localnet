"""ジョブ管理 — バックグラウンドタスク実行"""

import os
import sys
import json
import threading
import queue
import uuid
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config import CACHE_BASE
from crawler import WgetCrawler
from catalog_builder import build_catalog


class Job:
    def __init__(self):
        self.id = str(uuid.uuid4())[:8]
        self.status = 'pending'
        self.log_queue = queue.Queue(maxsize=1000)
        self.error = None
        self.domain = None
        self._crawler = None

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
        self.log_queue.put({"type": "done", "domain": self.domain, **extra})

    def fail(self, error):
        self.status = 'error'
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


def get_job(job_id):
    with _jobs_lock:
        return _jobs.get(job_id)


def stop_job(job_id):
    job = get_job(job_id)
    if job and job._crawler:
        job._crawler.stop()
        return True
    return False


def _start_job(target, *args):
    job = Job()
    with _jobs_lock:
        _jobs[job.id] = job
    threading.Thread(target=target, args=(job, *args), daemon=True).start()
    return job


# === ジョブ実行関数 ===

def _run_crawl(job, url, depth, delay, exclude):
    job.status = 'running'
    job.domain = urlparse(url).netloc
    try:
        crawler = WgetCrawler(
            url, max_depth=depth, delay=delay,
            log=job.log, exclude=exclude,
        )
        job._crawler = crawler
        job.domain = crawler.domain
        crawler.run()

        job.log("--- カタログ生成中 ---")
        build_catalog(crawler.domain, log=job.log)
        job.finish()
    except Exception as e:
        job.fail(e)
    finally:
        job._crawler = None


def _run_resume(job, domain):
    job.status = 'running'
    job.domain = domain
    try:
        cache_dir = os.path.join(CACHE_BASE, domain)
        if not os.path.isdir(cache_dir):
            raise FileNotFoundError(f'キャッシュなし: {domain}')

        start_url = f'https://{domain}/'
        crawler = WgetCrawler(
            start_url, max_depth=0, delay=1.0,
            log=job.log,
        )
        job._crawler = crawler
        job.log(f"再開: {domain}")
        crawler.run(resume=True)

        job.log("--- カタログ生成中 ---")
        build_catalog(domain, log=job.log)
        job.finish()
    except Exception as e:
        job.fail(e)
    finally:
        job._crawler = None


def _run_recrawl(job, domain):
    """キャッシュ削除 → 再クロール"""
    job.status = 'running'
    job.domain = domain
    try:
        import shutil
        cache_dir = os.path.join(CACHE_BASE, domain)
        if os.path.isdir(cache_dir):
            job.log(f"キャッシュ削除: {domain}")
            shutil.rmtree(cache_dir)

        start_url = f'https://{domain}/'
        crawler = WgetCrawler(
            start_url, max_depth=0, delay=1.0,
            log=job.log,
        )
        job._crawler = crawler
        job.log(f"再クロール開始: {domain}")
        crawler.run()

        job.log("--- カタログ生成中 ---")
        build_catalog(domain, log=job.log)
        job.finish()
    except Exception as e:
        job.fail(e)
    finally:
        job._crawler = None


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
