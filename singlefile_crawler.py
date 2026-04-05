"""SingleFileCrawler — 1ページ1ファイル完結のクローラー
CSS/画像をHTMLにインライン埋め込みして保存する。
パス解決問題が発生しない。"""

import os
import re
import time
import base64
import mimetypes
from collections import deque
from urllib.parse import urlparse, urljoin, unquote, quote

import requests
from bs4 import BeautifulSoup

from config import USER_AGENT, CACHE_BASE, AD_DOMAINS

_AD_SET = set(AD_DOMAINS)
_SESSION_TIMEOUT = 15


class SingleFileCrawler:
    def __init__(self, start_url, max_depth=0, delay=1.0,
                 log=None, exclude=None):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_depth = max_depth
        self.delay = delay
        self._log = log or print
        self.exclude = exclude or []

        self.cache_dir = os.path.join(CACHE_BASE, self.domain)
        os.makedirs(self.cache_dir, exist_ok=True)

        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate',
            'Referer': f'https://www.google.com/search?q={self.domain}',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'cross-site',
            'Sec-Fetch-User': '?1',
            'Sec-Ch-Ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
            'Sec-Ch-Ua-Mobile': '?1',
            'Sec-Ch-Ua-Platform': '"Android"',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        })
        self._session.verify = False
        self._stopped = False
        self.page_count = 0

        # リソースキャッシュ（同じCSS/画像を何度もDLしない、128MB上限）
        self._resource_cache = {}
        self._cache_size = 0
        self._cache_max = 128 * 1024 * 1024

    def stop(self):
        self._stopped = True

    def _is_excluded(self, url):
        lower = url.lower()
        if any(ad in lower for ad in _AD_SET):
            return True
        if re.search(r'(ads|tracking|affiliate|pixel|beacon|popup)', lower):
            return True
        for pat in self.exclude:
            if re.search(pat, url):
                return True
        return False

    def _is_same_domain(self, url):
        return urlparse(url).netloc == self.domain

    def _url_to_filepath(self, url):
        parsed = urlparse(url)
        path = unquote(parsed.path).lstrip('/')
        if not path or path.endswith('/'):
            path += 'index.html'
        if not os.path.splitext(path)[1]:
            path += '.html'
        return os.path.join(self.cache_dir, self.domain, path)

    def _fetch(self, url):
        """URLからコンテンツを取得。キャッシュあればそれを返す"""
        if url in self._resource_cache:
            return self._resource_cache[url]
        try:
            resp = self._session.get(url, timeout=_SESSION_TIMEOUT)
            if resp.status_code == 200:
                if self._cache_size + len(resp.content) <= self._cache_max:
                    self._resource_cache[url] = resp.content
                    self._cache_size += len(resp.content)
                return resp.content
        except Exception:
            pass
        return None

    def _fetch_and_encode_data_uri(self, url):
        """URLのリソースをdata URIに変換"""
        data = self._fetch(url)
        if not data:
            return None
        mime, _ = mimetypes.guess_type(url)
        if not mime:
            mime = self._detect_mime(data)
        b64 = base64.b64encode(data).decode('ascii')
        return f'data:{mime};base64,{b64}'

    def _detect_mime(self, data):
        if data.startswith(b'\x89PNG'):
            return 'image/png'
        if data.startswith(b'\xff\xd8\xff'):
            return 'image/jpeg'
        if data.startswith(b'GIF8'):
            return 'image/gif'
        if data[:4] == b'RIFF' and len(data) >= 12 and data[8:12] == b'WEBP':
            return 'image/webp'
        if data.startswith(b'<svg') or data.startswith(b'<?xml'):
            return 'image/svg+xml'
        return 'application/octet-stream'

    def _inline_css_resources(self, css_text, base_url):
        """CSS内のurl()参照をdata URIに置換"""
        def replace_url(match):
            raw = match.group(1).strip('\'"')
            if raw.startswith('data:'):
                return match.group(0)
            abs_url = urljoin(base_url, raw)
            data_uri = self._fetch_and_encode_data_uri(abs_url)
            if data_uri:
                return f'url({data_uri})'
            return match.group(0)

        return re.sub(r'url\(([^)]+)\)', replace_url, css_text)

    def _make_single_file(self, url, html_bytes):
        """HTMLの外部リソースを全てインライン化"""
        charset = 'utf-8'
        head = html_bytes[:4096].lower()
        m = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', head)
        if m:
            charset = m.group(1).decode('ascii', errors='ignore')

        html = html_bytes.decode(charset, errors='replace')
        soup = BeautifulSoup(html, 'html.parser')

        # 1. <link rel="stylesheet"> → <style>にインライン化
        for link in soup.find_all('link', rel=lambda r: r and 'stylesheet' in r):
            href = link.get('href')
            if not href:
                continue
            abs_url = urljoin(url, href)
            css_data = self._fetch(abs_url)
            if css_data:
                try:
                    css_text = css_data.decode('utf-8', errors='replace')
                except Exception:
                    continue
                css_text = self._inline_css_resources(css_text, abs_url)
                style_tag = soup.new_tag('style')
                style_tag.string = css_text
                link.replace_with(style_tag)

        # 2. <img src=""> → base64 data URI
        for img in soup.find_all(['img', 'amp-img']):
            src = img.get('src')
            if not src or src.startswith('data:'):
                continue
            abs_url = urljoin(url, src)
            data_uri = self._fetch_and_encode_data_uri(abs_url)
            if data_uri:
                img['src'] = data_uri
            srcset = img.get('srcset')
            if srcset:
                img['srcset'] = ''

        # 3. <style>内のurl()もインライン化
        for style in soup.find_all('style'):
            if style.string:
                style.string = self._inline_css_resources(style.string, url)

        # 4. CSS background-imageのインラインstyle内url()
        for tag in soup.find_all(style=True):
            style_val = tag['style']
            if 'url(' in style_val:
                tag['style'] = self._inline_css_resources(style_val, url)

        # 5. <script src=""> → インライン化（軽量なもののみ）
        for script in soup.find_all('script', src=True):
            src = script.get('src')
            if not src:
                continue
            abs_url = urljoin(url, src)
            js_data = self._fetch(abs_url)
            if js_data and len(js_data) < 500_000:
                try:
                    js_text = js_data.decode('utf-8', errors='replace')
                    script.string = js_text
                    del script['src']
                except Exception:
                    pass

        # 6. favicon
        for link in soup.find_all('link', rel=lambda r: r and 'icon' in ' '.join(r).lower()):
            href = link.get('href')
            if not href or href.startswith('data:'):
                continue
            abs_url = urljoin(url, href)
            data_uri = self._fetch_and_encode_data_uri(abs_url)
            if data_uri:
                link['href'] = data_uri

        return str(soup)

    def _extract_links(self, soup, base_url):
        """HTMLからリンクを抽出"""
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            abs_url = urljoin(base_url, href).split('#')[0]
            if self._is_same_domain(abs_url):
                links.append(abs_url)
        return links

    def run(self, resume=False):
        self._log(f"\U0001f680 クロール開始: {self.start_url}")
        self._log(f"\U0001f4c2 出力先: {self.cache_dir}")
        depth_str = '無制限' if self.max_depth == 0 else str(self.max_depth)
        self._log(f"\u23f1\ufe0f  遅延: {self.delay}s / 深さ: {depth_str}")
        self._log("(SingleFile crawler)")

        self.page_count = 0
        queue = deque([(self.start_url, 0)])
        visited = set()

        if resume:
            base = os.path.join(self.cache_dir, self.domain)
            if os.path.exists(base):
                existing = sum(1 for _, _, files in os.walk(base) for f in files)
                self.page_count = existing
                self._log(f"  既存 {existing} ファイル検出済み、新規のみ取得")

        while queue and not self._stopped:
            url, depth = queue.popleft()
            url = url.split('#')[0]
            if not url or url in visited:
                continue
            visited.add(url)

            if not self._is_same_domain(url):
                continue
            if self._is_excluded(url):
                continue
            if self.max_depth > 0 and depth > self.max_depth:
                continue

            filepath = self._url_to_filepath(url)

            if resume and os.path.exists(filepath):
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                        soup = BeautifulSoup(f.read(), 'html.parser')
                    for link in self._extract_links(soup, url):
                        if link not in visited:
                            queue.append((link, depth + 1))
                except Exception:
                    pass
                continue

            try:
                resp = self._session.get(url, timeout=_SESSION_TIMEOUT)
                if resp.status_code != 200:
                    self._log(f"\r[{self.page_count}] {resp.status_code} {unquote(url)[:70]}")
                    continue
                content_type = resp.headers.get('Content-Type', '')
                if 'html' not in content_type and not url.endswith('.html'):
                    continue
            except Exception as e:
                self._log(f"\r[{self.page_count}] ERR {unquote(url)[:60]}")
                continue

            try:
                single_html = self._make_single_file(url, resp.content)
            except Exception as e:
                self._log(f"\r[{self.page_count}] SingleFile化エラー: {e}")
                single_html = resp.text

            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(single_html)

            self.page_count += 1
            display = unquote(url)
            if len(display) > 75:
                display = display[:72] + '...'
            self._log(f"[{self.page_count}] {display}")

            try:
                soup = BeautifulSoup(single_html, 'html.parser')
                for link in self._extract_links(soup, url):
                    if link not in visited:
                        queue.append((link, depth + 1))
            except Exception:
                pass

            time.sleep(self.delay)

        if self._stopped:
            self._log(f"\u23f8\ufe0f 手動停止: {self.page_count} 件取得済み")
        else:
            self._log(f"\u2705 完了: {self.page_count} 件取得")

    def get_file_base(self):
        base = os.path.join(self.cache_dir, self.domain)
        if not os.path.exists(base):
            base = self.cache_dir
        return base
