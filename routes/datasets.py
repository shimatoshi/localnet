"""データセット管理API"""

import os
import re
import json
import shutil
import time
import tarfile
import zipfile
import tempfile
import threading
import requests as http_requests
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


# === 共有データセット（GitHub Releases） ===

SHARED_REPO = 'shimatoshi/localnet-datasets'
GH_TOKEN_PATH = os.path.expanduser('~/.config/gh/hosts.yml')  # gh CLIのトークン


def _get_gh_token():
    """gh CLIの認証トークンを取得"""
    # 環境変数優先
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    # gh CLIの設定から
    try:
        import subprocess
        result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None
_shared_cache = {'data': None, 'fetched_at': 0}
_shared_lock = threading.Lock()
_SHARED_TTL = 300  # 5分キャッシュ


def _fetch_shared():
    """GitHub ReleasesからデータセットをAPI取得（キャッシュ付き）"""
    now = time.time()
    with _shared_lock:
        if _shared_cache['data'] is not None and now - _shared_cache['fetched_at'] < _SHARED_TTL:
            return _shared_cache['data']

    try:
        r = http_requests.get(
            f'https://api.github.com/repos/{SHARED_REPO}/releases',
            headers={'Accept': 'application/vnd.github+json'},
            timeout=10,
        )
        if r.status_code != 200:
            return _shared_cache.get('data') or []

        releases = r.json()
        datasets = []
        for rel in releases:
            if rel.get('draft'):
                continue
            assets = rel.get('assets', [])
            for asset in assets:
                if not asset['name'].endswith(('.tar.gz', '.tgz', '.zip')):
                    continue
                ds_name = asset['name']
                for suffix in ('.tar.gz', '.tgz', '.zip'):
                    if ds_name.endswith(suffix):
                        ds_name = ds_name[:-len(suffix)]
                        break
                datasets.append({
                    'name': ds_name,
                    'filename': asset['name'],
                    'size': asset['size'],
                    'download_url': asset['browser_download_url'],
                    'description': rel.get('body', '') or rel.get('name', ''),
                    'published_at': rel.get('published_at', ''),
                    'tag': rel.get('tag_name', ''),
                })

        with _shared_lock:
            _shared_cache['data'] = datasets
            _shared_cache['fetched_at'] = now
        return datasets
    except Exception:
        return _shared_cache.get('data') or []


@bp.route('/api/datasets/shared')
def api_shared_datasets():
    """共有データセット一覧"""
    return jsonify(_fetch_shared())


@bp.route('/api/datasets/shared/download', methods=['POST'])
def api_download_shared():
    """共有データセットをDL→ローカルにインポート"""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()
    if not url or not name:
        return jsonify({"error": "urlとnameが必要です"}), 400

    _ensure_dir()

    try:
        r = http_requests.get(url, stream=True, timeout=60)
        if r.status_code != 200:
            return jsonify({"error": f"ダウンロード失敗: HTTP {r.status_code}"}), 502

        # 一時ファイルに保存
        suffix = '.tar.gz' if '.tar.gz' in url else '.zip'
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        for chunk in r.iter_content(8192):
            tmp.write(chunk)
        tmp.close()

        # 展開
        if suffix == '.zip':
            with zipfile.ZipFile(tmp.name, 'r') as zf:
                members = zf.namelist()
                for m in members:
                    if m.startswith('/') or '..' in m:
                        raise ValueError("不正なパス")
                top = members[0].split('/')[0] if members else name
                zf.extractall(DATASETS_DIR)
        else:
            with tarfile.open(tmp.name, 'r:*') as tar:
                members = tar.getnames()
                for m in members:
                    if m.startswith('/') or '..' in m:
                        raise ValueError("不正なパス")
                top = members[0].split('/')[0] if members else name
                try:
                    tar.extractall(path=DATASETS_DIR, filter='data')
                except TypeError:
                    tar.extractall(path=DATASETS_DIR)

        os.unlink(tmp.name)

        # メタデータ補完
        ds_dir = os.path.join(DATASETS_DIR, top)
        if os.path.isdir(ds_dir) and not os.path.isfile(os.path.join(ds_dir, 'dataset.json')):
            _save_meta(ds_dir, {
                'name': top,
                'description': f'共有データセットからDL',
                'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
            })

        # カタログ生成
        for site_name in os.listdir(ds_dir):
            site_dir = os.path.join(ds_dir, site_name)
            if not os.path.isdir(site_dir) or site_name == 'dataset.json':
                continue
            if not os.path.isfile(os.path.join(site_dir, 'catalog.json')):
                try:
                    _build_catalog_for(site_dir, site_name)
                except Exception:
                    pass

        return jsonify({"ok": True, "name": top})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# === アップロード（GitHub Releasesに公開） ===

@bp.route('/api/datasets/<ds_name>/upload', methods=['POST'])
def api_upload_dataset(ds_name):
    """データセットをtar.gz化してGitHub Releasesにアップロード"""
    ds_dir = os.path.join(DATASETS_DIR, _sanitize(ds_name))
    if not os.path.isdir(ds_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404

    token = _get_gh_token()
    if not token:
        return jsonify({"error": "GitHubトークンが設定されていません。GH_TOKEN環境変数を設定してください。"}), 400

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
    }

    try:
        # tar.gz作成（シンボリックリンクを実ファイルとして追加）
        tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
        with tarfile.open(tmp.name, 'w:gz', dereference=True) as tar:
            tar.add(ds_dir, arcname=ds_name)
        tmp.close()

        tag = f'{ds_name}-{time.strftime("%Y%m%d%H%M%S")}'
        meta = _load_meta(ds_dir)
        description = meta.get('description', '') or ds_name

        # Release作成
        r = http_requests.post(
            f'https://api.github.com/repos/{SHARED_REPO}/releases',
            headers=headers,
            json={
                'tag_name': tag,
                'name': f'{ds_name}',
                'body': description,
                'draft': False,
            },
            timeout=15,
        )
        if r.status_code not in (200, 201):
            os.unlink(tmp.name)
            return jsonify({"error": f"Release作成失敗: {r.status_code} {r.text[:200]}"}), 502

        release = r.json()
        upload_url = release['upload_url'].replace('{?name,label}', '')

        # assetアップロード
        file_size = os.path.getsize(tmp.name)
        with open(tmp.name, 'rb') as f:
            r = http_requests.post(
                f'{upload_url}?name={ds_name}.tar.gz',
                headers={
                    **headers,
                    'Content-Type': 'application/gzip',
                    'Content-Length': str(file_size),
                },
                data=f,
                timeout=300,
            )

        os.unlink(tmp.name)

        if r.status_code not in (200, 201):
            return jsonify({"error": f"アップロード失敗: {r.status_code}"}), 502

        # キャッシュクリア
        with _shared_lock:
            _shared_cache['data'] = None
            _shared_cache['fetched_at'] = 0

        return jsonify({"ok": True, "tag": tag, "url": release['html_url']})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
