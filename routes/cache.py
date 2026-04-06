"""キャッシュファイル配信"""

import os
import mimetypes
from flask import Blueprint, request, jsonify, send_file, make_response
from urllib.parse import unquote

from config import CACHE_BASE
from utils import detect_charset, detect_mime_from_bytes, is_valid_domain

bp = Blueprint('cache', __name__)


def _find_file(base, subpath):
    """ファイルを探す。クエリパラメータ付きファイル名にもフォールバック"""
    filepath = os.path.realpath(os.path.join(base, subpath))
    real_base = os.path.realpath(base)
    if not filepath.startswith(real_base + os.sep) and filepath != real_base:
        return None

    # そのまま存在する場合
    if os.path.isfile(filepath):
        return filepath

    # wgetがクエリパラメータ込みで保存したファイルを探す
    # 例: classic.css?v=234b1a7c.css, style.css?ver=6.1
    parent = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    if os.path.isdir(parent):
        for fname in os.listdir(parent):
            # basename で始まり ? を含むファイル
            if fname.startswith(basename + '?') or fname.startswith(basename + '%3F'):
                candidate = os.path.join(parent, fname)
                if os.path.isfile(candidate):
                    return candidate

    return None


@bp.route('/api/cache/<domain>/<path:subpath>')
def api_cache(domain, subpath):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400

    subpath = unquote(subpath)
    base = os.path.join(CACHE_BASE, domain)

    # 新フォーマット: subpath/index.html を試す
    filepath = _find_file(base, os.path.join(subpath, 'index.html'))
    # 直接ファイルとして試す
    if not filepath:
        filepath = _find_file(base, subpath)
    # 旧フォーマット: domain/domain/subpath
    if not filepath:
        old_base = os.path.join(CACHE_BASE, domain, domain)
        if os.path.isdir(old_base):
            filepath = _find_file(old_base, subpath)
    # 拡張子なしURLに .html フォールバック
    if not filepath and not os.path.splitext(subpath)[1]:
        filepath = _find_file(base, subpath.rstrip('/') + '.html')
    if not filepath:
        return '', 404

    mime, _ = mimetypes.guess_type(filepath)
    if not mime:
        try:
            with open(filepath, 'rb') as f:
                head = f.read(256)
            mime = detect_mime_from_bytes(head) or 'application/octet-stream'
        except Exception:
            mime = 'application/octet-stream'

    if mime and mime.startswith('text/html'):
        try:
            with open(filepath, 'rb') as f:
                head = f.read(4096)
            charset = detect_charset(head)
            if charset:
                mime = f'text/html; charset={charset}'
        except Exception:
            pass

    response = make_response(send_file(filepath, mimetype=mime))
    response.headers['Content-Type'] = mime
    return response
