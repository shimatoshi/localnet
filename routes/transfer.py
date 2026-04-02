"""エクスポート/インポート"""

import os
import tarfile
import tempfile
from flask import Blueprint, request, jsonify, send_file

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
