"""クロール・ジョブ操作API + SSEストリーミング"""

import json
import time
import queue
from flask import Blueprint, request, jsonify, Response

from utils import is_valid_domain

from jobs import (
    get_job, stop_job, start_crawl_job, start_resume_job,
    start_build_job, start_recrawl_job,
    _jobs, _jobs_lock,
)

bp = Blueprint('crawl', __name__)


@bp.route('/api/crawl', methods=['POST'])
def api_crawl():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "リクエストボディが不正です"}), 400
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"error": "URLを指定してください"}), 400

    try:
        depth = int(data.get('depth', 0))
    except (ValueError, TypeError):
        depth = 0
    if depth < 0:
        depth = 0
    try:
        delay = max(0.5, min(float(data.get('delay', 1.0)), 30.0))
    except (ValueError, TypeError):
        delay = 1.0
    exclude = data.get('exclude', [])
    if isinstance(exclude, str):
        exclude = [p.strip() for p in exclude.split(',') if p.strip()]

    job = start_crawl_job(url, depth, delay, exclude)
    return jsonify(job.to_dict())


@bp.route('/api/resume/<domain>', methods=['POST'])
def api_resume(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_resume_job(domain)
    return jsonify(job.to_dict())


@bp.route('/api/recrawl/<domain>', methods=['POST'])
def api_recrawl(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_recrawl_job(domain)
    return jsonify(job.to_dict())


@bp.route('/api/build/<domain>', methods=['POST'])
def api_build(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    job = start_build_job(domain)
    return jsonify(job.to_dict())


@bp.route('/api/jobs/<job_id>/stop', methods=['POST'])
def api_stop(job_id):
    if stop_job(job_id):
        return jsonify({"ok": True})
    return jsonify({"error": "ジョブが見つからないか停止できません"}), 404


@bp.route('/api/jobs/active')
def api_active_jobs():
    with _jobs_lock:
        active = [j.to_dict() for j in _jobs.values() if j.status == 'running']
    return jsonify(active)


@bp.route('/api/jobs/<job_id>/stream')
def api_stream(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404

    def generate():
        max_duration = 86400
        start_time = time.time()
        while time.time() - start_time < max_duration:
            try:
                msg = job.log_queue.get(timeout=30)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                if msg.get('type') in ('done', 'error'):
                    break
            except queue.Empty:
                yield f"data: {json.dumps({'type': 'ping'})}\n\n"
                if job.status in ('done', 'error'):
                    break
        else:
            yield f"data: {json.dumps({'type': 'error', 'message': 'タイムアウト（24時間）'})}\n\n"

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@bp.route('/api/jobs/<job_id>')
def api_job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "ジョブが見つかりません"}), 404
    return jsonify(job.to_dict())
