"""検索・カタログ・サイト一覧API"""

import os
from flask import Blueprint, request, jsonify, send_file

from config import CACHE_BASE
from utils import is_valid_domain
from catalog_builder import search_catalogs, search_images
from jobs import get_all_sites

bp = Blueprint('search', __name__)


@bp.route('/api/search')
def api_search():
    q = request.args.get('q', '').strip()
    try:
        limit = int(request.args.get('limit', 50))
    except (ValueError, TypeError):
        limit = 50
    if not q:
        return jsonify([])
    return jsonify(search_catalogs(q, limit=limit))


@bp.route('/api/search/images')
def api_search_images():
    q = request.args.get('q', '').strip()
    try:
        limit = int(request.args.get('limit', 50))
    except (ValueError, TypeError):
        limit = 50
    if not q:
        return jsonify([])
    return jsonify(search_images(q, limit=limit))


@bp.route('/api/catalog/<domain>')
def api_catalog(domain):
    if not is_valid_domain(domain):
        return jsonify({"error": "不正なドメイン名です"}), 400
    catalog_path = os.path.join(CACHE_BASE, domain, 'catalog.json')
    if not os.path.isfile(catalog_path):
        return jsonify({"error": "カタログが見つかりません"}), 404
    return send_file(catalog_path, mimetype='application/json')


@bp.route('/api/sites')
def api_sites():
    return jsonify(get_all_sites())


@bp.route('/api/sites/versions')
def api_sites_versions():
    versions = {}
    if os.path.isdir(CACHE_BASE):
        for name in os.listdir(CACHE_BASE):
            catalog = os.path.join(CACHE_BASE, name, 'catalog.json')
            if os.path.isfile(catalog):
                versions[name] = int(os.path.getmtime(catalog))
    return jsonify(versions)
