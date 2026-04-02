"""共通ユーティリティ — MIME検出・charset検出・バリデーション"""

import re

_DOMAIN_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


def is_valid_domain(domain: str) -> bool:
    """ドメイン名のバリデーション"""
    return bool(_DOMAIN_RE.match(domain))


def detect_charset(raw_head):
    """HTMLバイト列(先頭数KB)からcharsetを検出。見つからなければNone"""
    head = raw_head[:4096].lower()
    # <meta charset="...">
    m = re.search(rb'<meta\s[^>]*charset=["\']?([a-zA-Z0-9_-]+)', head)
    if m:
        return m.group(1).decode('ascii', errors='ignore')
    # <meta http-equiv="content-type" content="text/html; charset=...">
    m = re.search(rb'content-type[^>]*charset=([a-zA-Z0-9_-]+)', head)
    if m:
        return m.group(1).decode('ascii', errors='ignore')
    return None


def detect_mime_from_bytes(data):
    """バイト列先頭からMIMEタイプを推定。判定不能ならNone"""
    if len(data) < 4:
        return None
    if data.startswith(b'\x89PNG'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data.startswith(b'GIF8'):
        return 'image/gif'
    if data[:4] == b'RIFF' and len(data) >= 12 and data[8:12] == b'WEBP':
        return 'image/webp'
    head_lower = data[:256].lower()
    if b'<html' in head_lower or b'<!doctype' in head_lower:
        return 'text/html'
    return None
