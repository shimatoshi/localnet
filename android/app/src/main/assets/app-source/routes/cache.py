"""キャッシュファイル配信"""

import os
import re
import gzip as _gzip
import mimetypes
from flask import Blueprint, request, jsonify, send_file, make_response
from urllib.parse import unquote

from config import CACHE_BASE, FONTS_BASE
from utils import detect_charset, detect_mime_from_bytes, is_valid_domain

try:
    import brotli as _brotli
    _BROTLI_OK = True
except ImportError:
    _BROTLI_OK = False


def _read_file_decompressed(filepath, max_bytes=None):
    """ファイル内容を読む。.gz/.brは自動解凍。max_bytesで先頭だけ読む。"""
    if filepath.endswith('.br') and _BROTLI_OK:
        with open(filepath, 'rb') as f:
            data = _brotli.decompress(f.read())
        return data[:max_bytes] if max_bytes else data
    elif filepath.endswith('.gz'):
        with _gzip.open(filepath, 'rb') as f:
            return f.read(max_bytes) if max_bytes else f.read()
    else:
        with open(filepath, 'rb') as f:
            return f.read(max_bytes) if max_bytes else f.read()

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
    """ファイルを探す。クエリパラメータ付きファイル名にもフォールバック。
    .br > .gz > 無圧縮 の順で優先。"""
    filepath = os.path.realpath(os.path.join(base, subpath))
    real_base = os.path.realpath(base)
    if not filepath.startswith(real_base + os.sep) and filepath != real_base:
        return None

    # brotli圧縮版を優先
    br_path = filepath + '.br'
    if os.path.isfile(br_path):
        return br_path

    # gzip圧縮版
    gz_path = filepath + '.gz'
    if os.path.isfile(gz_path):
        return gz_path

    # そのまま存在する場合
    if os.path.isfile(filepath):
        return filepath

    # wgetがクエリパラメータ込みで保存したファイルを探す
    parent = os.path.dirname(filepath)
    basename = os.path.basename(filepath)
    if os.path.isdir(parent):
        for fname in os.listdir(parent):
            if fname.startswith(basename + '?') or fname.startswith(basename + '%3F'):
                candidate = os.path.join(parent, fname)
                if os.path.isfile(candidate):
                    return candidate

    # 共有リソースディレクトリにフォールバック
    shared_dir = os.path.join(base, '_shared')
    if os.path.isdir(shared_dir):
        # br > gz > 無圧縮
        for suffix in ('.br', '.gz', ''):
            sp = os.path.join(shared_dir, basename + suffix)
            if os.path.isfile(sp):
                return sp

    return None


@bp.route('/api/cache/<domain>/<path:subpath>')
def api_cache(domain, subpath):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400

    subpath = unquote(subpath)
    base = os.path.join(CACHE_BASE, domain)

    # 拡張子なし or '/'終端ならディレクトリ扱いで index.html を優先
    looks_like_dir = subpath.endswith('/') or not os.path.splitext(subpath)[1]
    if looks_like_dir:
        filepath = _find_file(base, os.path.join(subpath, 'index.html'))
    else:
        filepath = None
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

    is_br = filepath.endswith('.br')
    is_gz = filepath.endswith('.gz')
    # 圧縮ファイルの場合、本来の拡張子でMIME判定
    if is_br or is_gz:
        mime_path = filepath[:-3] if is_gz else filepath[:-3]
    else:
        mime_path = filepath

    mime, _ = mimetypes.guess_type(mime_path)
    if not mime:
        try:
            head = _read_file_decompressed(filepath, max_bytes=256)
            mime = detect_mime_from_bytes(head) or 'application/octet-stream'
        except Exception:
            mime = 'application/octet-stream'

    if mime and mime.startswith('text/html'):
        try:
            head = _read_file_decompressed(filepath, max_bytes=4096)
            charset = detect_charset(head) or 'utf-8'
            mime = f'text/html; charset={charset}'
        except Exception:
            pass

    # CSSファイルの場合、フォントURLを共有パスに書き換え
    if mime and 'css' in mime:
        try:
            raw = _read_file_decompressed(filepath)
            charset = detect_charset(raw[:4096]) or 'utf-8'
            css_text = raw.decode(charset, errors='replace')
            css_text = _rewrite_font_urls(css_text)
            response = make_response(css_text)
            response.headers['Content-Type'] = f'text/css; charset={charset}'
            return response
        except Exception:
            pass

    # 圧縮ファイルはContent-Encodingで返す
    # クライアントが対応してなければ解凍して返す
    accept_enc = request.headers.get('Accept-Encoding', '')
    if is_br:
        if 'br' in accept_enc:
            with open(filepath, 'rb') as f:
                data = f.read()
            response = make_response(data)
            response.headers['Content-Type'] = mime
            response.headers['Content-Encoding'] = 'br'
            return response
        else:
            # クライアント未対応 → 解凍して返す
            data = _read_file_decompressed(filepath)
            response = make_response(data)
            response.headers['Content-Type'] = mime
            return response

    if is_gz:
        if 'gzip' in accept_enc:
            with open(filepath, 'rb') as f:
                data = f.read()
            response = make_response(data)
            response.headers['Content-Type'] = mime
            response.headers['Content-Encoding'] = 'gzip'
            return response
        else:
            data = _read_file_decompressed(filepath)
            response = make_response(data)
            response.headers['Content-Type'] = mime
            return response

    response = make_response(send_file(filepath, mimetype=mime))
    response.headers['Content-Type'] = mime
    return response
