"""エクスポート/インポート"""

import os
import re
import tarfile
import tempfile
from flask import Blueprint, request, jsonify, send_file
from werkzeug.utils import secure_filename

from config import CACHE_BASE
from utils import is_valid_domain
from jobs import start_import_job

bp = Blueprint('transfer', __name__)


@bp.route('/api/export/<domain>')
def api_export(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        return jsonify({"error": "キャッシュが見つかりません"}), 404

    tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
    try:
        with tarfile.open(tmp.name, 'w:gz') as tar:
            tar.add(cache_dir, arcname=domain)
        resp = send_file(
            tmp.name,
            as_attachment=True,
            download_name=f"{domain}.tar.gz",
            mimetype='application/gzip',
        )

        @resp.call_on_close
        def _cleanup():
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

        return resp
    except Exception as e:
        os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 500


@bp.route('/api/import', methods=['POST'])
def api_import():
    if 'file' not in request.files:
        return jsonify({"error": "ファイルが指定されていません"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "ファイル名がありません"}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
    try:
        f.save(tmp.name)
        with tarfile.open(tmp.name, 'r:*') as tar:
            members = tar.getnames()
            if not members:
                os.unlink(tmp.name)
                return jsonify({"error": "空のアーカイブです"}), 400
            for m in members:
                if m.startswith('/') or '..' in m:
                    os.unlink(tmp.name)
                    return jsonify({"error": "不正なパスがアーカイブに含まれています"}), 400
            domain = members[0].split('/')[0]
            if not is_valid_domain(domain):
                os.unlink(tmp.name)
                return jsonify({"error": f"不正なドメイン名: {domain}"}), 400
            try:
                tar.extractall(path=CACHE_BASE, filter='data')
            except TypeError:
                # Python < 3.12: filter パラメータ未対応
                tar.extractall(path=CACHE_BASE)

        os.unlink(tmp.name)
        job = start_import_job(domain)
        return jsonify(job.to_dict())
    except tarfile.TarError as e:
        os.unlink(tmp.name)
        return jsonify({"error": f"アーカイブ解凍エラー: {e}"}), 400
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 500


def _sanitize_name(name):
    """データセット名をファイルシステムセーフにする"""
    name = re.sub(r'[^\w\-.]', '_', name.strip())
    return name or 'unnamed'


@bp.route('/api/import-local', methods=['POST'])
def api_import_local():
    """ローカルHTMLファイル群をデータセットとしてインポート"""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({"error": "データセット名が必要です"}), 400

    dataset_name = _sanitize_name(name)
    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "ファイルが指定されていません"}), 400

    # cache/<dataset_name>/<dataset_name>/ に保存
    cache_dir = os.path.join(CACHE_BASE, dataset_name)
    base_dir = os.path.join(cache_dir, dataset_name)
    os.makedirs(base_dir, exist_ok=True)

    saved = 0
    for f in files:
        if not f.filename:
            continue
        # ディレクトリ構造を維持（webkitdirectory対応）
        filename = f.filename.replace('\\', '/')
        # 最初のディレクトリ名を除去（フォルダ選択時のルートフォルダ名）
        parts = filename.split('/')
        if len(parts) > 1:
            filename = '/'.join(parts[1:])
        safe_path = os.path.normpath(filename)
        if safe_path.startswith('..') or safe_path.startswith('/'):
            continue
        dest = os.path.join(base_dir, safe_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        saved += 1

    if saved == 0:
        return jsonify({"error": "保存できるファイルがありませんでした"}), 400

    job = start_import_job(dataset_name)
    return jsonify({**job.to_dict(), "saved_files": saved})
