"""データセット共有API — GitHub Releases経由のデータセット共有"""

import os
import json
import shutil
import time
import tarfile
import zipfile
import tempfile
import threading
import requests as http_requests
from flask import Blueprint, request, jsonify, send_file

from config import CACHE_BASE

bp = Blueprint('datasets', __name__)

DATASETS_DIR = os.path.join(os.path.dirname(CACHE_BASE), 'datasets')


def _ensure_dir():
    os.makedirs(DATASETS_DIR, exist_ok=True)


# === GitHub共有 ===

SHARED_REPO = 'shimatoshi/localnet-datasets'


def _get_gh_token():
    """gh CLIの認証トークンを取得"""
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    try:
        import subprocess
        result = subprocess.run(['gh', 'auth', 'token'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


_shared_lock = threading.Lock()


def _shared_list_path():
    _ensure_dir()
    return os.path.join(DATASETS_DIR, 'shared_list.json')


def _load_shared_list():
    path = _shared_list_path()
    if os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_shared_list(data):
    with open(_shared_list_path(), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _fetch_shared_from_github():
    """GitHub Releasesから最新リストを取得してローカルに保存"""
    try:
        r = http_requests.get(
            f'https://api.github.com/repos/{SHARED_REPO}/releases',
            headers={'Accept': 'application/vnd.github+json'},
            timeout=10,
        )
        if r.status_code != 200:
            return None

        releases = r.json()
        datasets = []
        for rel in releases:
            if rel.get('draft'):
                continue
            assets = rel.get('assets', [])
            if not assets:
                continue
            asset = assets[0]
            ds_name = rel.get('name', '') or rel.get('tag_name', '')
            if any(d['name'] == ds_name for d in datasets):
                continue
            datasets.append({
                'name': ds_name,
                'filename': asset['name'],
                'size': asset['size'],
                'download_url': asset['browser_download_url'],
                'description': rel.get('body', '') or '',
                'published_at': rel.get('published_at', ''),
                'tag': rel.get('tag_name', ''),
            })

        with _shared_lock:
            _save_shared_list(datasets)
        return datasets
    except Exception:
        return None


@bp.route('/api/datasets/shared')
def api_shared_datasets():
    """共有データセット一覧"""
    return jsonify(_load_shared_list())


@bp.route('/api/datasets/shared/refresh', methods=['POST'])
def api_refresh_shared():
    """GitHub Releasesから最新を取得してリスト更新"""
    result = _fetch_shared_from_github()
    if result is None:
        return jsonify({"error": "GitHub APIからの取得に失敗しました"}), 502
    return jsonify({"ok": True, "count": len(result)})


@bp.route('/api/datasets/shared/download', methods=['POST'])
def api_download_shared():
    """共有データセットをDL→cache/に展開"""
    data = request.get_json(silent=True) or {}
    url = data.get('url', '').strip()
    name = data.get('name', '').strip()
    if not url or not name:
        return jsonify({"error": "urlとnameが必要です"}), 400

    try:
        r = http_requests.get(url, stream=True, timeout=60)
        if r.status_code != 200:
            return jsonify({"error": f"ダウンロード失敗: HTTP {r.status_code}"}), 502

        tmp = tempfile.NamedTemporaryFile(suffix='.bin', delete=False)
        for chunk in r.iter_content(8192):
            tmp.write(chunk)
        tmp.close()

        # 中身で判定
        with open(tmp.name, 'rb') as f:
            magic = f.read(4)
        is_zip = magic[:2] == b'PK'

        if is_zip:
            with zipfile.ZipFile(tmp.name, 'r') as zf:
                members = zf.namelist()
                for m in members:
                    if os.path.isabs(m) or os.path.normpath(m).startswith('..'):
                        raise ValueError("不正なパス")
                top = members[0].split('/')[0] if members else name
                zf.extractall(CACHE_BASE)
        else:
            with tarfile.open(tmp.name, 'r:*') as tar:
                members = tar.getnames()
                for m in members:
                    if os.path.isabs(m) or os.path.normpath(m).startswith('..'):
                        raise ValueError("不正なパス")
                top = members[0].split('/')[0] if members else name
                try:
                    tar.extractall(path=CACHE_BASE, filter='data')
                except TypeError:
                    tar.extractall(path=CACHE_BASE)

        os.unlink(tmp.name)

        # カタログ生成
        from catalog_builder import build_catalog
        try:
            build_catalog(top)
        except Exception:
            pass

        return jsonify({"ok": True, "name": top})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route('/api/datasets/<domain>/upload', methods=['POST'])
def api_upload_dataset(domain):
    """cache/のデータセットをtar.gz化してGitHub Releasesにアップロード"""
    cache_dir = os.path.join(CACHE_BASE, domain)
    if not os.path.isdir(cache_dir):
        return jsonify({"error": "データセットが見つかりません"}), 404

    token = _get_gh_token()
    if not token:
        return jsonify({"error": "GitHubトークンが設定されていません"}), 400

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github+json',
    }

    try:
        tmp = tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False)
        with tarfile.open(tmp.name, 'w:gz', dereference=True) as tar:
            tar.add(cache_dir, arcname=domain)
        tmp.close()

        tag = f'{domain}-{time.strftime("%Y%m%d%H%M%S")}'

        r = http_requests.post(
            f'https://api.github.com/repos/{SHARED_REPO}/releases',
            headers=headers,
            json={
                'tag_name': tag,
                'name': domain,
                'body': f'Dataset: {domain}',
                'draft': False,
            },
            timeout=15,
        )
        if r.status_code not in (200, 201):
            os.unlink(tmp.name)
            return jsonify({"error": f"Release作成失敗: {r.status_code}"}), 502

        release = r.json()
        upload_url = release['upload_url'].replace('{?name,label}', '')

        file_size = os.path.getsize(tmp.name)
        with open(tmp.name, 'rb') as f:
            r = http_requests.post(
                f'{upload_url}?name={domain}.tar.gz',
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

        _fetch_shared_from_github()
        return jsonify({"ok": True, "tag": tag, "url": release['html_url']})

    except Exception as e:
        return jsonify({"error": str(e)}), 500
