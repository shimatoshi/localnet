"""キャッシュファイル配信"""

import os
import re
import mimetypes
from flask import Blueprint, jsonify, send_file, make_response
from urllib.parse import unquote

from config import CACHE_BASE
from utils import detect_charset, detect_mime_from_bytes, is_valid_domain

bp = Blueprint('cache', __name__)


@bp.route('/api/cache/<domain>/<path:subpath>')
def api_cache(domain, subpath):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400

    subpath = unquote(subpath)

    base = os.path.join(CACHE_BASE, domain, domain)
    if not os.path.isdir(base):
        base = os.path.join(CACHE_BASE, domain)

    filepath = os.path.realpath(os.path.join(base, subpath))
    if not filepath.startswith(os.path.realpath(base) + os.sep):
        return jsonify({"error": "不正なパスです"}), 400

    if not os.path.isfile(filepath):
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
