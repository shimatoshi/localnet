"""キャッシュファイル配信"""

import os
import re
import mimetypes
from flask import Blueprint, request, jsonify, send_file, make_response
from urllib.parse import unquote

from config import CACHE_BASE, FONTS_BASE
from utils import detect_charset, detect_mime_from_bytes, is_valid_domain

# 共有フォントに存在するファイル名セット（起動時にロード）
_shared_fonts = set()

def _load_shared_fonts():
    global _shared_fonts
    if os.path.isdir(FONTS_BASE):
        _shared_fonts = {f for f in os.listdir(FONTS_BASE)
                         if os.path.splitext(f)[1].lower()
                         in ('.woff2', '.woff', '.ttf', '.eot', '.svg', '.otf')}

_load_shared_fonts()

# url(ファイル名) を /_shared/fonts/ファイル名 に書き換え
_FONT_URL_RE = re.compile(r'url\((["\']?)([^)"\':]+\.(?:woff2|woff|ttf|eot|svg|otf))\1\)')

def _rewrite_font_urls(css_text):
    """CSS内のフォントURLを共有フォントパスに書き換え"""
    if not _shared_fonts:
        _load_shared_fonts()
    def _replace(m):
        quote = m.group(1)
        filename = m.group(2)
        # パスからファイル名部分だけ取得
        basename = filename.rsplit('/', 1)[-1] if '/' in filename else filename
        if basename in _shared_fonts:
            return f'url({quote}/_shared/fonts/{basename}{quote})'
        return m.group(0)
    return _FONT_URL_RE.sub(_replace, css_text)

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

    # gzip圧縮版を探す（.gz付き）
    gz_path = filepath + '.gz'
    if os.path.isfile(gz_path):
        return gz_path

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

    # 共有リソースディレクトリにフォールバック
    shared_dir = os.path.join(base, '_shared')
    if os.path.isdir(shared_dir):
        shared_path = os.path.join(shared_dir, basename)
        if os.path.isfile(shared_path):
            return shared_path
        # 共有ディレクトリ内のgz版
        shared_gz = shared_path + '.gz'
        if os.path.isfile(shared_gz):
            return shared_gz

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

    is_gz = filepath.endswith('.gz')
    # gzファイルの場合、本来の拡張子でMIME判定
    mime_path = filepath[:-3] if is_gz else filepath

    mime, _ = mimetypes.guess_type(mime_path)
    if not mime:
        try:
            if is_gz:
                import gzip as _gzip
                with _gzip.open(filepath, 'rb') as f:
                    head = f.read(256)
            else:
                with open(filepath, 'rb') as f:
                    head = f.read(256)
            mime = detect_mime_from_bytes(head) or 'application/octet-stream'
        except Exception:
            mime = 'application/octet-stream'

    if mime and mime.startswith('text/html'):
        try:
            if is_gz:
                import gzip as _gzip
                with _gzip.open(filepath, 'rb') as f:
                    head = f.read(4096)
            else:
                with open(filepath, 'rb') as f:
                    head = f.read(4096)
            charset = detect_charset(head) or 'utf-8'
            mime = f'text/html; charset={charset}'
        except Exception:
            pass

    # CSSファイルの場合、フォントURLを共有パスに書き換え
    if mime and 'css' in mime:
        try:
            if is_gz:
                import gzip as _gzip
                with _gzip.open(filepath, 'rb') as f:
                    raw = f.read()
            else:
                with open(filepath, 'rb') as f:
                    raw = f.read()
            charset = detect_charset(raw[:4096]) or 'utf-8'
            css_text = raw.decode(charset, errors='replace')
            css_text = _rewrite_font_urls(css_text)
            response = make_response(css_text)
            response.headers['Content-Type'] = f'text/css; charset={charset}'
            return response
        except Exception:
            pass

    # gzファイルはContent-Encoding: gzipで返す
    if is_gz:
        with open(filepath, 'rb') as f:
            data = f.read()
        response = make_response(data)
        response.headers['Content-Type'] = mime
        response.headers['Content-Encoding'] = 'gzip'
        return response

    response = make_response(send_file(filepath, mimetype=mime))
    response.headers['Content-Type'] = mime
    return response
