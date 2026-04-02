"""jobs.py のテスト"""

import sys
import os
import time
import queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jobs import Job, _jobs, _jobs_lock, _purge_old_jobs, get_job, _JOB_TTL


class TestJob:
    def test_initial_state(self):
        job = Job()
        assert job.status == 'pending'
        assert job.error is None
        assert job.domain is None
        assert len(job.id) == 8

    def test_log(self):
        job = Job()
        job.log("hello")
        item = job.log_queue.get_nowait()
        assert item == {"type": "log", "message": "hello"}

    def test_finish(self):
        job = Job()
        job.domain = "example.com"
        job.finish()
        assert job.status == 'done'
        assert job._finished_at is not None
        msg = job.log_queue.get_nowait()
        assert msg["type"] == "done"
        assert msg["domain"] == "example.com"

    def test_fail(self):
        job = Job()
        job.fail("something broke")
        assert job.status == 'error'
        assert job.error == "something broke"
        assert job._finished_at is not None
        msg = job.log_queue.get_nowait()
        assert msg["type"] == "error"
        assert msg["message"] == "something broke"

    def test_to_dict(self):
        job = Job()
        job.domain = "test.org"
        d = job.to_dict()
        assert d['job_id'] == job.id
        assert d['status'] == 'pending'
        assert d['domain'] == 'test.org'
        assert d['page_count'] == 0
        assert d['error'] is None

    def test_log_overflow(self):
        """log_queue is maxsize=1000; old messages are dropped when full"""
        job = Job()
        for i in range(1010):
            job.log(f"msg-{i}")
        count = 0
        while not job.log_queue.empty():
            job.log_queue.get_nowait()
            count += 1
        assert count == 1000


class TestPurgeOldJobs:
    def setup_method(self):
        """Clear global job store before each test"""
        with _jobs_lock:
            _jobs.clear()

    def teardown_method(self):
        with _jobs_lock:
            _jobs.clear()

    def test_purge_removes_expired(self):
        job = Job()
        job.status = 'done'
        job._finished_at = time.time() - _JOB_TTL - 10
        with _jobs_lock:
            _jobs[job.id] = job
            _purge_old_jobs()
            assert job.id not in _jobs

    def test_purge_keeps_recent(self):
        job = Job()
        job.status = 'done'
        job._finished_at = time.time() - 10
        with _jobs_lock:
            _jobs[job.id] = job
            _purge_old_jobs()
            assert job.id in _jobs

    def test_purge_keeps_running(self):
        job = Job()
        job.status = 'running'
        job._finished_at = None
        with _jobs_lock:
            _jobs[job.id] = job
            _purge_old_jobs()
            assert job.id in _jobs


class TestGetJob:
    def setup_method(self):
        with _jobs_lock:
            _jobs.clear()

    def teardown_method(self):
        with _jobs_lock:
            _jobs.clear()

    def test_get_existing(self):
        job = Job()
        with _jobs_lock:
            _jobs[job.id] = job
        assert get_job(job.id) is job

    def test_get_nonexistent(self):
        assert get_job("nonexistent") is None
