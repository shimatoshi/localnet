"""共有フォント配信"""

import os
from flask import Blueprint, send_from_directory, jsonify

from config import FONTS_BASE

bp = Blueprint('fonts', __name__)

FONT_MIMES = {
    '.woff2': 'font/woff2',
    '.woff': 'font/woff',
    '.ttf': 'font/ttf',
    '.eot': 'application/vnd.ms-fontobject',
    '.svg': 'image/svg+xml',
    '.otf': 'font/otf',
}


@bp.route('/_shared/fonts/<path:filename>')
def serve_font(filename):
    ext = os.path.splitext(filename)[1].lower()
    mime = FONT_MIMES.get(ext, 'application/octet-stream')
    response = send_from_directory(FONTS_BASE, filename, mimetype=mime)
    response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response


@bp.route('/_shared/fonts/')
def list_fonts():
    if not os.path.isdir(FONTS_BASE):
        return jsonify([])
    fonts = [f for f in os.listdir(FONTS_BASE)
             if os.path.splitext(f)[1].lower() in FONT_MIMES]
    return jsonify(sorted(fonts))
