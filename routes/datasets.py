"""データセット管理API"""

import os
import re
import json
import shutil
import time
import tarfile
import zipfile
import tempfile
from flask import Blueprint, request, jsonify, send_file

from config import CACHE_BASE, SITES_BASE

bp = Blueprint('datasets', __name__)

DATASETS_DIR = os.path.join(os.path.dirname(CACHE_BASE), 'datasets')


def _ensure_dir():
    os.makedirs(DATASETS_DIR, exist_ok=True)


def _sanitize(name):
    name = re.sub(r'[^\w\-.]', '_', name.strip())
    return name or 'unnamed'


def _load_meta(ds_dir):
    meta_path = os.path.join(ds_dir, 'dataset.json')
    if os.path.isfile(meta_path):
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_meta(ds_dir, meta):
    with open(os.path.join(ds_dir, 'dataset.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _list_sites(ds_dir):
    """データセット内のサイト一覧"""
    sites = []
    for name in sorted(os.listdir(ds_dir)):
        site_dir = os.path.join(ds_dir, name)
        if not os.path.isdir(site_dir) or name.startswith('.'):
            continue
        # dataset.jsonはスキップ
        if name == 'dataset.json':
            continue

        file_count = sum(1 for _, _, files in os.walk(site_dir) for f in files)
        catalog_path = os.path.join(site_dir, 'catalog.json')
        page_count = 0
        if os.path.isfile(catalog_path):
            try:
                with open(catalog_path, 'r') as f:
                    page_count = len(json.load(f))
            except Exception:
                pass

        # クロール済み(cache参照)か自作か判定
        source = 'custom'
        cache_link = os.path.join(site_dir, '.cache_ref')
        if os.path.isfile(cache_link):
            source = 'crawled'

        sites.append({
            'name': name,
            'file_count': file_count,
            'page_count': page_count,
            'source': source,
        })
    return sites


# === データセット CRUD ===

@bp.route('/api/datasets')
def api_list_datasets():
    _ensure_dir()
    datasets = []
    for name in sorted(os.listdir(DATASETS_DIR)):
        ds_dir = os.path.join(DATASETS_DIR, name)
        if not os.path.isdir(ds_dir):
            continue
        meta = _load_meta(ds_dir)
        sites = _list_sites(ds_dir)
        datasets.append({
            'name': name,
            'description': meta.get('description', ''),
            'created_at': meta.get('created_at', ''),
            'site_count': len(sites),
            'sites': sites,
        })
    return jsonify(datasets)


@bp.route('/api/datasets/create', methods=['POST'])
def api_create_dataset():
    data = request.get_json(silent=True) or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({"error": "名前が必要です"}), 400

    ds_name = _sanitize(name)
    ds_dir = os.path.join(DATASETS_DIR, ds_name)
    if os.path.exists(ds_dir):
        return jsonify({"error": f"既に存在します: {ds_name}"}), 400

    os.makedirs(ds_dir, exist_ok=True)
    _save_meta(ds_dir, {
        'name': name,
        'description': data.get('description', ''),
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    })
    return jsonify({"name": ds_name})


@bp.route('/api/datasets/<ds_name>')
def api_get_dataset(ds_name):
    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    if not os.path.isdir(ds_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404
    meta = _load_meta(ds_dir)
    sites = _list_sites(ds_dir)
    return jsonify({
        'name': ds_name,
        'description': meta.get('description', ''),
        'created_at': meta.get('created_at', ''),
        'sites': sites,
    })


@bp.route('/api/datasets/<ds_name>/delete', methods=['POST'])
def api_delete_dataset(ds_name):
    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    if not os.path.isdir(ds_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404
    shutil.rmtree(ds_dir)
    return jsonify({"ok": True})


# === データセット内サイト管理 ===

@bp.route('/api/datasets/<ds_name>/add-crawled', methods=['POST'])
def api_add_crawled(ds_name):
    """クロール済みサイトをデータセットに追加（シンボリックリンク）"""
    data = request.get_json(silent=True) or {}
    domain = data.get('domain', '').strip()
    if not domain:
        return jsonify({"error": "ドメインが必要です"}), 400

    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        return jsonify({"error": f"キャッシュが見つかりません: {domain}"}), 404

    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    if not os.path.isdir(ds_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404

    site_dir = os.path.join(ds_dir, domain)
    if os.path.exists(site_dir):
        return jsonify({"error": f"既に追加済み: {domain}"}), 400

    # シンボリックリンクで参照（容量節約）
    try:
        os.symlink(cache_dir, site_dir)
    except OSError:
        # シンボリックリンクが使えない環境ではコピー
        shutil.copytree(cache_dir, site_dir)

    return jsonify({"ok": True, "domain": domain})


@bp.route('/api/datasets/<ds_name>/add-template', methods=['POST'])
def api_add_template_site(ds_name):
    """テンプレートからサイトを作成してデータセットに追加"""
    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    if not os.path.isdir(ds_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404

    form_data = request.form.get('data', '')
    if not form_data:
        return jsonify({"error": "データがありません"}), 400
    try:
        site_data = json.loads(form_data)
    except json.JSONDecodeError:
        return jsonify({"error": "JSONパースエラー"}), 400

    name = site_data.get('name', '').strip()
    if not name:
        return jsonify({"error": "サイト名が必要です"}), 400

    site_name = _sanitize(name)
    content_dir = os.path.join(ds_dir, site_name, site_name)
    os.makedirs(content_dir, exist_ok=True)

    # ファイルを保存
    uploaded = {}
    for key in request.files:
        f = request.files[key]
        if f.filename:
            safe = re.sub(r'[^\w.\-]', '_', f.filename)
            dest = os.path.join(content_dir, 'files', safe)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            f.save(dest)
            uploaded[key] = f'files/{safe}'

    # HTML生成
    pages = site_data.get('pages', [])
    if not pages:
        return jsonify({"error": "ページが必要です"}), 400

    from routes.sites import _render_page, _build_site_catalog_in
    nav_items = []
    for i, page in enumerate(pages):
        slug = page.get('slug', '').strip() or f'page{i+1}'
        slug = re.sub(r'[^\w\-]', '_', slug)
        title = page.get('title', slug)
        nav_items.append((slug, title))

    for i, page in enumerate(pages):
        slug = nav_items[i][0]
        title = page.get('title', slug)
        body = page.get('body', '')
        images = page.get('images', [])
        attachments = page.get('attachments', [])

        html = _render_page(site_name, title, body, images, attachments,
                            uploaded, nav_items, i)
        filename = 'index.html' if i == 0 else f'{slug}.html'
        with open(os.path.join(content_dir, filename), 'w', encoding='utf-8') as f:
            f.write(html)

    _build_site_catalog_in(os.path.join(ds_dir, site_name), site_name)
    return jsonify({"name": site_name, "pages": len(pages)})


@bp.route('/api/datasets/<ds_name>/remove-site', methods=['POST'])
def api_remove_site(ds_name):
    """データセットからサイトを削除"""
    data = request.get_json(silent=True) or {}
    site_name = data.get('name', '').strip()
    if not site_name:
        return jsonify({"error": "サイト名が必要です"}), 400

    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    site_dir = os.path.join(ds_dir, site_name)

    if os.path.islink(site_dir):
        os.unlink(site_dir)
    elif os.path.isdir(site_dir):
        shutil.rmtree(site_dir)
    else:
        return jsonify({"error": "サイトが見つかりません"}), 404

    return jsonify({"ok": True})


# === エクスポート（tar.gz化） ===

@bp.route('/api/datasets/<ds_name>/export')
def api_export_dataset(ds_name):
    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    if not os.path.isdir(ds_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404

    tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
    try:
        with tarfile.open(tmp.name, 'w:gz') as tar:
            tar.add(ds_dir, arcname=ds_name, filter=_tar_deref_filter)
        resp = send_file(tmp.name, as_attachment=True,
                         download_name=f"{ds_name}.tar.gz", mimetype='application/gzip')

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


def _tar_deref_filter(tarinfo):
    """シンボリックリンクを実ファイルとして追加"""
    return tarinfo


# === インポート（tar.gz/zip → データセットとして追加） ===

@bp.route('/api/datasets/import', methods=['POST'])
def api_import_dataset():
    if 'file' not in request.files:
        return jsonify({"error": "ファイルが必要です"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "ファイル名がありません"}), 400

    _ensure_dir()
    tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(f.filename)[1], delete=False)
    try:
        f.save(tmp.name)
        name_lower = tmp.name.lower()

        if name_lower.endswith('.zip'):
            with zipfile.ZipFile(tmp.name, 'r') as zf:
                members = zf.namelist()
                if not members:
                    raise ValueError("空のアーカイブ")
                for m in members:
                    if m.startswith('/') or '..' in m:
                        raise ValueError("不正なパス")
                top = members[0].split('/')[0]
                zf.extractall(DATASETS_DIR)
        else:
            with tarfile.open(tmp.name, 'r:*') as tar:
                members = tar.getnames()
                if not members:
                    raise ValueError("空のアーカイブ")
                for m in members:
                    if m.startswith('/') or '..' in m:
                        raise ValueError("不正なパス")
                top = members[0].split('/')[0]
                try:
                    tar.extractall(path=DATASETS_DIR, filter='data')
                except TypeError:
                    tar.extractall(path=DATASETS_DIR)

        os.unlink(tmp.name)

        # dataset.jsonがなければ作成
        ds_dir = os.path.join(DATASETS_DIR, top)
        if os.path.isdir(ds_dir) and not os.path.isfile(os.path.join(ds_dir, 'dataset.json')):
            _save_meta(ds_dir, {
                'name': top,
                'description': 'インポート',
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            })

        # カタログがないサイトにはカタログ生成
        for name in os.listdir(ds_dir):
            site_dir = os.path.join(ds_dir, name)
            if not os.path.isdir(site_dir) or name == 'dataset.json':
                continue
            cat = os.path.join(site_dir, 'catalog.json')
            if not os.path.isfile(cat):
                try:
                    from catalog_builder import build_catalog
                    # catalog_builderはCACHE_BASE前提なので、一時的にパスを合わせる
                    _build_catalog_for(site_dir, name)
                except Exception:
                    pass

        return jsonify({"name": top})

    except (ValueError, tarfile.TarError, zipfile.BadZipFile) as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
        return jsonify({"error": str(e)}), 500


def _build_catalog_for(site_dir, name):
    """任意ディレクトリのカタログ生成"""
    import mimetypes
    from urllib.parse import quote
    from utils import detect_charset

    base = os.path.join(site_dir, name)
    if not os.path.isdir(base):
        base = site_dir

    catalog = []
    for root, _, files in os.walk(base):
        for fname in files:
            filepath = os.path.join(root, fname)
            mime, _ = mimetypes.guess_type(filepath)
            is_html = mime and 'html' in mime
            if not is_html:
                try:
                    with open(filepath, 'rb') as f:
                        head = f.read(256).lower()
                    is_html = b'<html' in head or b'<!doctype' in head
                except Exception:
                    pass
            if not is_html:
                continue

            relpath = os.path.relpath(filepath, base).replace(os.sep, '/')
            title = ''
            try:
                with open(filepath, 'rb') as f:
                    head = f.read(8192)
                charset = detect_charset(head) or 'utf-8'
                html = head.decode(charset, errors='replace')
                import re
                m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
                if m:
                    title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
            except Exception:
                pass
            catalog.append({'url': f'https://{name}/{relpath}', 'title': title or relpath, 'path': relpath})

    with open(os.path.join(site_dir, 'catalog.json'), 'w', encoding='utf-8') as f:
        json.dump(catalog, f, ensure_ascii=False)
