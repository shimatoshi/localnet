"""HTML/CSS/SVG minify — コメント・連続空白の除去。

pre/textarea/script/style 内は保護（HTML）。
"""

import os
import re

# HTML
_HTML_PROTECTED_RE = re.compile(
    r'(<(pre|textarea|script|style)\b[^>]*>.*?</\2>)',
    re.IGNORECASE | re.DOTALL)
_HTML_COMMENT_RE = re.compile(r'<!--(?!\s*\[if\b).*?-->', re.DOTALL)
_HTML_TAG_WS_RE = re.compile(r'>\s+<')
_HTML_MULTI_WS_RE = re.compile(r'\s{2,}')


def minify_html(text):
    protected = []

    def _protect(m):
        protected.append(m.group(1))
        return f'\x00HTMLPROT{len(protected) - 1}\x00'

    text = _HTML_PROTECTED_RE.sub(_protect, text)
    text = _HTML_COMMENT_RE.sub('', text)
    text = _HTML_TAG_WS_RE.sub('><', text)
    text = _HTML_MULTI_WS_RE.sub(' ', text)
    text = text.strip()
    for i, content in enumerate(protected):
        text = text.replace(f'\x00HTMLPROT{i}\x00', content, 1)
    return text


# CSS
_CSS_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_CSS_WS_RE = re.compile(r'\s+')
_CSS_TRIM_RE = re.compile(r'\s*([{}:;,>+~])\s*')
_CSS_LAST_SEMI_RE = re.compile(r';}')


def minify_css(text):
    text = _CSS_COMMENT_RE.sub('', text)
    text = _CSS_WS_RE.sub(' ', text)
    text = _CSS_TRIM_RE.sub(r'\1', text)
    text = _CSS_LAST_SEMI_RE.sub('}', text)
    return text.strip()


# SVG
_SVG_COMMENT_RE = re.compile(r'<!--.*?-->', re.DOTALL)
_SVG_XML_DECL_RE = re.compile(r'<\?xml[^>]*\?>\s*')
_SVG_DOCTYPE_RE = re.compile(r'<!DOCTYPE[^>]*>\s*', re.IGNORECASE)
_SVG_WS_RE = re.compile(r'>\s+<')
_SVG_MULTI_WS_RE = re.compile(r'\s{2,}')


def minify_svg(text):
    text = _SVG_XML_DECL_RE.sub('', text)
    text = _SVG_DOCTYPE_RE.sub('', text)
    text = _SVG_COMMENT_RE.sub('', text)
    text = _SVG_WS_RE.sub('><', text)
    text = _SVG_MULTI_WS_RE.sub(' ', text)
    return text.strip()


_MIN_SIZE = 256  # これ以下はオーバーヘッド勝ちするのでスキップ

_HANDLERS = {
    '.html': minify_html,
    '.htm': minify_html,
    '.css': minify_css,
    '.svg': minify_svg,
}


def minify_text_files(site_dir, log):
    stats = {'minified': 0, 'bytes_saved': 0}
    for root, dirs, files in os.walk(site_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext not in _HANDLERS:
                continue
            fpath = os.path.join(root, f)
            try:
                size = os.path.getsize(fpath)
                if size < _MIN_SIZE:
                    continue
                with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
                    text = fh.read()
                new_text = _HANDLERS[ext](text)
                new_bytes = new_text.encode('utf-8')
                if len(new_bytes) < size and len(new_bytes) > 0:
                    with open(fpath, 'wb') as fh:
                        fh.write(new_bytes)
                    stats['minified'] += 1
                    stats['bytes_saved'] += size - len(new_bytes)
            except Exception:
                pass
    if stats['minified']:
        log(f"[compactor] minify: {stats['minified']}件 "
            f"({stats['bytes_saved'] / 1024:.1f}KB節約)")
    else:
        log("[compactor] minify対象なし")
    return stats
