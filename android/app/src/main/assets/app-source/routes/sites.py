"""shimanetサイト — ユーザー自作サイトの管理"""

import os
import re
import json
import shutil
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from config import SITES_BASE, CACHE_BASE
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
    os.makedirs(site_dir, exist_ok=True)

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
        dest = os.path.join(site_dir, safe_path)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        f.save(dest)
        saved += 1

    if saved == 0:
        return jsonify({"error": "保存できるファイルがありませんでした"}), 400

    _sync_to_cache(site_name)
    build_catalog(site_name)
    return jsonify({"name": site_name, "saved_files": saved})


@bp.route('/api/sites/custom/create-from-template', methods=['POST'])
def api_create_from_template():
    """テンプレートからサイトを生成"""
    data = request.form.get('data', '')
    if not data:
        return jsonify({"error": "データがありません"}), 400
    try:
        site_data = json.loads(data)
    except json.JSONDecodeError:
        return jsonify({"error": "JSONパースエラー"}), 400

    name = site_data.get('name', '').strip()
    if not name:
        return jsonify({"error": "サイト名が必要です"}), 400

    site_name = _sanitize_site_name(name)
    pages = site_data.get('pages', [])
    if not pages:
        return jsonify({"error": "ページが1つ以上必要です"}), 400

    site_dir = os.path.join(SITES_BASE, site_name)
    os.makedirs(site_dir, exist_ok=True)

    # 各ページのslugを先に決定
    nav_items = []
    for i, page in enumerate(pages):
        slug = page.get('slug', '').strip() or f'page{i+1}'
        slug = re.sub(r'[^\w\-]', '_', slug)
        title = page.get('title', slug)
        nav_items.append((slug, title))

    # 各ページをフォルダ形式で生成
    for i, page in enumerate(pages):
        slug = nav_items[i][0]
        title = page.get('title', slug)
        body = page.get('body', '')
        images = page.get('images', [])
        attachments = page.get('attachments', [])

        # ページディレクトリ: トップは_root、それ以外はslug名
        page_dir_name = '_root' if i == 0 else slug
        page_dir = os.path.join(site_dir, page_dir_name)
        os.makedirs(page_dir, exist_ok=True)

        # ファイルをページディレクトリに保存
        uploaded = {}
        for key in images + attachments:
            if key in request.files:
                f = request.files[key]
                if f.filename:
                    safe = re.sub(r'[^\w.\-]', '_', f.filename)
                    dest = os.path.join(page_dir, safe)
                    f.save(dest)
                    uploaded[key] = safe

        html = _render_page(site_name, title, body, images, attachments,
                            uploaded, nav_items, i)

        with open(os.path.join(page_dir, 'index.html'), 'w', encoding='utf-8') as f:
            f.write(html)

    _sync_to_cache(site_name)
    build_catalog(site_name)
    return jsonify({"name": site_name, "pages": len(pages)})


def _render_page(site_name, title, body, images, attachments,
                 uploaded, nav_items, current_idx):
    """1ページ分のHTMLを生成"""
    from html import escape

    # ナビゲーション（フォルダ形式: 各ページは ../slug/index.html）
    nav_html = '<nav class="site-nav">'
    for i, (slug, nav_title) in enumerate(nav_items):
        href = '../_root/index.html' if i == 0 else f'../{slug}/index.html'
        cls = ' class="active"' if i == current_idx else ''
        nav_html += f'<a href="{href}"{cls}>{escape(nav_title)}</a>'
    nav_html += '</nav>'

    # 本文（改行をbrに）
    body_html = ''
    if body:
        for line in body.split('\n'):
            line = line.strip()
            if not line:
                body_html += '<br>'
            elif line.startswith('# '):
                body_html += f'<h2>{escape(line[2:])}</h2>'
            elif line.startswith('## '):
                body_html += f'<h3>{escape(line[3:])}</h3>'
            elif line.startswith('- '):
                body_html += f'<li>{escape(line[2:])}</li>'
            else:
                body_html += f'<p>{escape(line)}</p>'

    # 画像（同フォルダ内の相対パス）
    images_html = ''
    for key in images:
        if key in uploaded:
            fname = uploaded[key]
            images_html += f'<figure><img src="{escape(fname)}" alt="" loading="lazy"></figure>'

    # 添付ファイル（同フォルダ内の相対パス）
    attach_html = ''
    if attachments:
        attach_html = '<div class="attachments"><h3>添付ファイル</h3><ul>'
        for key in attachments:
            if key in uploaded:
                fname = uploaded[key]
                attach_html += f'<li><a href="{escape(fname)}" download>{escape(fname)}</a></li>'
        attach_html += '</ul></div>'

    return f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)} - {escape(site_name)}</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       line-height: 1.7; color: #333; background: #fafafa; max-width: 800px;
       margin: 0 auto; padding: 16px; }}
h1 {{ font-size: 1.5em; margin: 16px 0 8px; }}
h2 {{ font-size: 1.3em; margin: 20px 0 8px; color: #1a1a2e; }}
h3 {{ font-size: 1.1em; margin: 16px 0 6px; }}
p {{ margin: 6px 0; }}
li {{ margin-left: 24px; }}
img {{ max-width: 100%; height: auto; border-radius: 4px; }}
figure {{ margin: 12px 0; }}
a {{ color: #2563eb; }}
.site-nav {{ display: flex; gap: 8px; flex-wrap: wrap; padding: 12px 0;
             border-bottom: 1px solid #ddd; margin-bottom: 16px; }}
.site-nav a {{ text-decoration: none; padding: 4px 12px; border-radius: 4px;
               background: #e8e8e8; color: #333; font-size: 0.9em; }}
.site-nav a.active {{ background: #2563eb; color: #fff; }}
.attachments {{ margin-top: 24px; padding: 12px; background: #f0f0f0;
                border-radius: 6px; }}
.attachments ul {{ margin-left: 20px; }}
</style>
</head>
<body>
{nav_html}
<h1>{escape(title)}</h1>
{body_html}
{images_html}
{attach_html}
</body>
</html>'''


@bp.route('/api/sites/custom/delete/<name>', methods=['POST'])
def api_delete_site(name):
    site_name = _sanitize_site_name(name)
    site_dir = os.path.join(SITES_BASE, site_name)
    if not os.path.isdir(site_dir):
        return jsonify({"error": "サイトが見つかりません"}), 404
    shutil.rmtree(site_dir)
    return jsonify({"ok": True})


@bp.route('/api/sites/custom/serve/<name>/<path:path>')
def api_serve_site(name, path):
    site_name = _sanitize_site_name(name)
    site_dir = os.path.join(SITES_BASE, site_name)
    return send_from_directory(site_dir, path)


@bp.route('/api/sites/custom/catalog/<name>')
def api_site_catalog(name):
    site_name = _sanitize_site_name(name)
    catalog_path = os.path.join(SITES_BASE, site_name, 'catalog.json')
    if not os.path.isfile(catalog_path):
        return jsonify([])
    from flask import send_file
    return send_file(catalog_path, mimetype='application/json')


def _sync_to_cache(site_name):
    """自作サイトをcache/にシンボリックリンクで配置"""
    site_dir = os.path.join(SITES_BASE, site_name)
    cache_dest = os.path.join(CACHE_BASE, site_name)
    if os.path.islink(cache_dest):
        os.unlink(cache_dest)
    elif os.path.isdir(cache_dest):
        shutil.rmtree(cache_dest)
    try:
        os.symlink(site_dir, cache_dest)
    except OSError:
        shutil.copytree(site_dir, cache_dest)
