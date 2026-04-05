"""エクスポート/インポート"""

import os
import re
import tarfile
import zipfile
import tempfile
from flask import Blueprint, request, jsonify, send_file

from config import CACHE_BASE
from utils import is_valid_domain
from jobs import start_import_job

bp = Blueprint('transfer', __name__)

# インポートフォルダ（APK環境: /sdcard/ShimaNet/import/）
IMPORT_DIR = os.environ.get('SHIMANET_IMPORT_DIR',
                            os.path.join(os.path.dirname(CACHE_BASE), 'import'))


def _extract_archive(filepath, dest_dir):
    """zip/tar.gz/tar を dest_dir に展開。トップレベルのフォルダ名を返す"""
    name_lower = filepath.lower()
    if name_lower.endswith('.zip'):
        with zipfile.ZipFile(filepath, 'r') as zf:
            members = zf.namelist()
            if not members:
                raise ValueError("空のアーカイブです")
            for m in members:
                if os.path.isabs(m) or os.path.normpath(m).startswith('..'):
                    raise ValueError("不正なパスがアーカイブに含まれています")
            top = members[0].split('/')[0]
            zf.extractall(dest_dir)
            return top
    else:
        with tarfile.open(filepath, 'r:*') as tar:
            members = tar.getnames()
            if not members:
                raise ValueError("空のアーカイブです")
            for m in members:
                if os.path.isabs(m) or os.path.normpath(m).startswith('..'):
                    raise ValueError("不正なパスがアーカイブに含まれています")
            top = members[0].split('/')[0]
            try:
                tar.extractall(path=dest_dir, filter='data')
            except TypeError:
                tar.extractall(path=dest_dir)
            return top


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
            tmp.name, as_attachment=True,
            download_name=f"{domain}.tar.gz", mimetype='application/gzip',
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
    """zip/tar.gz ファイルをアップロードしてインポート"""
    if 'file' not in request.files:
        return jsonify({"error": "ファイルが指定されていません"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "ファイル名がありません"}), 400

    tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(f.filename)[1], delete=False)
    try:
        f.save(tmp.name)
        domain = _extract_archive(tmp.name, CACHE_BASE)
        os.unlink(tmp.name)
        if not is_valid_domain(domain):
            return jsonify({"error": f"不正なドメイン名: {domain}"}), 400
        job = start_import_job(domain)
        return jsonify(job.to_dict())
    except (ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 500


@bp.route('/api/import/scan')
def api_import_scan():
    """インポートフォルダのファイル一覧"""
    files = []
    if os.path.isdir(IMPORT_DIR):
        for name in sorted(os.listdir(IMPORT_DIR)):
            lower = name.lower()
            if lower.endswith(('.zip', '.tar.gz', '.tgz', '.tar')):
                filepath = os.path.join(IMPORT_DIR, name)
                size = os.path.getsize(filepath)
                files.append({"name": name, "size": size, "path": filepath})
    return jsonify({"import_dir": IMPORT_DIR, "files": files})


@bp.route('/api/import/folder/<filename>', methods=['POST'])
def api_import_from_folder(filename):
    """インポートフォルダ内の指定ファイルをインポート"""
    safe_name = os.path.basename(filename)
    filepath = os.path.join(IMPORT_DIR, safe_name)
    if not os.path.isfile(filepath):
        return jsonify({"error": f"ファイルが見つかりません: {filename}"}), 404
    try:
        domain = _extract_archive(filepath, CACHE_BASE)
        if not is_valid_domain(domain):
            return jsonify({"error": f"不正なドメイン名: {domain}"}), 400
        job = start_import_job(domain)
        return jsonify(job.to_dict())
    except (ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _sanitize_name(name):
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

    cache_dir = os.path.join(CACHE_BASE, dataset_name)
    base_dir = os.path.join(cache_dir, dataset_name)
    os.makedirs(base_dir, exist_ok=True)

    saved = 0
    for f in files:
        if not f.filename:
            continue
        filename = f.filename.replace('\\', '/')
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
