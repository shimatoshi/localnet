"""shimanetサイト — ユーザー自作サイトの管理"""

import os
import re
import json
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from config import SITES_BASE
from catalog_builder import build_catalog
from jobs import start_import_job

bp = Blueprint('sites', __name__)


def _sanitize_site_name(name):
    name = re.sub(r'[^\w\-.]', '_', name.strip().lower())
    return name or 'unnamed'


def _get_site_info():
    """全自作サイト一覧"""
    sites = []
    if not os.path.exists(SITES_BASE):
        return sites
    for name in sorted(os.listdir(SITES_BASE)):
        site_dir = os.path.join(SITES_BASE, name)
        if not os.path.isdir(site_dir):
            continue
        file_count = sum(1 for _, _, files in os.walk(site_dir) for f in files)
        # catalog.jsonがあればページ数取得
        catalog_path = os.path.join(site_dir, 'catalog.json')
        page_count = 0
        if os.path.exists(catalog_path):
            try:
                with open(catalog_path, 'r') as f:
                    page_count = len(json.load(f))
            except Exception:
                pass
        sites.append({
            "name": name,
            "file_count": file_count,
            "page_count": page_count,
        })
    return sites


@bp.route('/api/sites/custom')
def api_custom_sites():
    return jsonify(_get_site_info())


@bp.route('/api/sites/custom/create', methods=['POST'])
def api_create_site():
    """自作サイトを作成（HTMLファイルのアップロード）"""
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({"error": "サイト名が必要です"}), 400

    site_name = _sanitize_site_name(name)
    files = request.files.getlist('files')
    if not files:
        return jsonify({"error": "ファイルが指定されていません"}), 400

    site_dir = os.path.join(SITES_BASE, site_name)
    content_dir = os.path.join(site_dir, site_name)
    os.makedirs(content_dir, exist_ok=True)

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
        dest = os.path.join(content_dir, safe_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        saved += 1

    if saved == 0:
        return jsonify({"error": "保存できるファイルがありませんでした"}), 400

    # カタログ生成（sitesディレクトリ用）
    _build_site_catalog(site_name)

    return jsonify({"name": site_name, "saved_files": saved})


@bp.route('/api/sites/custom/delete/<name>', methods=['POST'])
def api_delete_site(name):
    site_name = _sanitize_site_name(name)
    site_dir = os.path.join(SITES_BASE, site_name)
    if not os.path.isdir(site_dir):
        return jsonify({"error": "サイトが見つかりません"}), 404
    import shutil
    shutil.rmtree(site_dir)
    return jsonify({"ok": True})


@bp.route('/api/sites/custom/serve/<name>/<path:path>')
def api_serve_site(name, path):
    site_name = _sanitize_site_name(name)
    content_dir = os.path.join(SITES_BASE, site_name, site_name)
    if not os.path.isdir(content_dir):
        content_dir = os.path.join(SITES_BASE, site_name)
    return send_from_directory(content_dir, path)


@bp.route('/api/sites/custom/catalog/<name>')
def api_site_catalog(name):
    site_name = _sanitize_site_name(name)
    catalog_path = os.path.join(SITES_BASE, site_name, 'catalog.json')
    if not os.path.isfile(catalog_path):
        return jsonify([])
    from flask import send_file
    return send_file(catalog_path, mimetype='application/json')


def _build_site_catalog(site_name):
    """自作サイト用のカタログを生成"""
    import mimetypes
    from urllib.parse import quote

    site_dir = os.path.join(SITES_BASE, site_name)
    content_dir = os.path.join(site_dir, site_name)
    if not os.path.isdir(content_dir):
        content_dir = site_dir

    catalog = []
    for root, _, files in os.walk(content_dir):
        for fname in files:
            filepath = os.path.join(root, fname)
            mime, _ = mimetypes.guess_type(filepath)
            is_html = False
            if mime and 'html' in mime:
                is_html = True
            else:
                try:
                    with open(filepath, 'rb') as f:
                        head = f.read(256).lower()
                    is_html = b'<html' in head or b'<!doctype' in head
                except Exception:
                    pass
            if not is_html:
                continue

            relpath = os.path.relpath(filepath, content_dir).replace(os.sep, '/')
            title = ''
            try:
                with open(filepath, 'rb') as f:
                    head = f.read(8192)
                html = head.decode('utf-8', errors='replace')
                m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                if m:
                    title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            except Exception:
                pass

            url = f'shimanet://{site_name}/{quote(relpath, safe="/:@!$&()*+,;=-._~")}'
            catalog.append({
                'url': url,
                'title': title or relpath,
                'path': relpath,
            })

    catalog_path = os.path.join(site_dir, 'catalog.json')
    with open(catalog_path, 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False)
    return catalog
