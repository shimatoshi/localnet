"""PageDirCrawler — 1ページ1フォルダ式クローラー
ページごとにフォルダを作り、HTML・CSS・画像・JSをファイルとして保存。
HTMLの参照は同フォルダ内の相対パスに書き換える。
Base64変換・BS4によるインライン化が不要なため軽量。"""

import os
import re
import time
import hashlib
import mimetypes
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin, unquote

import java_http

from config import USER_AGENT, CACHE_BASE, AD_DOMAINS

_AD_SET = set(AD_DOMAINS)
_SESSION_TIMEOUT = 15
_RESOURCE_TIMEOUT = (1, 2)  # (connect, read) timeout
_SKIP_EXT = {'.gif', '.mp4', '.webm', '.ogv', '.mpeg', '.mov', '.avi', '.js'}
_MAX_RPS = 4  # 秒間リクエスト上限（リソースDL含む全体）
_BACKOFF_CODES = {429, 503}  # バックオフ対象ステータス
_BACKOFF_STEPS = [5, 10, 30, 60]  # 段階的バックオフ秒数


class _RateLimiter:
    """トークンバケット方式のレートリミッター"""
    def __init__(self, rps):
        self._interval = 1.0 / rps
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self):
        with self._lock:
            now = time.time()
            wait_time = self._last + self._interval - now
            if wait_time > 0:
                time.sleep(wait_time)
            self._last = time.time()


class Crawler:

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

        self._headers = {
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
        }
        self._stopped = False
        self.page_count = 0

        # リソースキャッシュ（同じCSS/画像を何度もDLしない）
        self._fetched_resources = {}  # url -> ローカルファイル名
        # バックグラウンドリソースDLプール
        self._bg_pool = ThreadPoolExecutor(max_workers=2)
        self._bg_futures = []
        # レートリミッター（リソースDL含む全リクエスト共通）
        self._limiter = _RateLimiter(_MAX_RPS)
        self._backoff_count = 0

    def stop(self):
        self._stopped = True

    def _do_backoff(self):
        """429/503時の段階的バックオフ"""
        idx = min(self._backoff_count, len(_BACKOFF_STEPS) - 1)
        wait = _BACKOFF_STEPS[idx]
        self._log(f"  ⏳ サーバー過負荷検知、{wait}秒待機...")
        time.sleep(wait)
        self._backoff_count += 1

    def _is_ad_resource(self, url):
        lower = url.lower()
        if any(ad in lower for ad in _AD_SET):
            return True
        if re.search(r'(ads|tracking|affiliate|pixel|beacon|popup)', lower):
            return True
        return False

    def _is_excluded(self, url):
        if self._is_ad_resource(url):
            return True
        for pat in self.exclude:
            if re.search(pat, url):
                return True
        return False

    def _is_same_domain(self, url):
        return urlparse(url).netloc == self.domain

    def _is_skip_resource(self, url):
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        return ext in _SKIP_EXT

    def _url_to_page_dir(self, url):
        """URLからページ用ディレクトリパスを生成"""
        parsed = urlparse(url)
        path = unquote(parsed.path).strip('/')
        if not path:
            path = '_root'
        # .html/.htm等で終わるパスは拡張子を除去（ファイルとディレクトリの衝突回避）
        if re.search(r'\.(html?|php|asp|jsp|cgi)$', path, re.IGNORECASE):
            path = re.sub(r'\.[^/]+$', '', path)
        # パスをそのままディレクトリにする
        safe_path = re.sub(r'[<>:"|?*]', '_', path)
        return os.path.join(self.cache_dir, safe_path)

    def _resource_filename(self, url):
        """リソースURLからファイル名を生成"""
        parsed = urlparse(url)
        basename = os.path.basename(unquote(parsed.path))
        if not basename:
            basename = 'resource'
        # 同名衝突回避のためハッシュを付ける
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        name, ext = os.path.splitext(basename)
        if not ext:
            ext = ''
        safe_name = re.sub(r'[<>:"|?*]', '_', name)[:50]
        return f'{safe_name}_{url_hash}{ext}'

    _MAX_RESOURCES_PER_PAGE = 200

    def _fetch_resource(self, url, page_dir):
        """リソースをDLしてpage_dir内に保存。ローカルファイル名を返す"""
        if self._is_ad_resource(url) or self._is_skip_resource(url):
            return None

        # ページ単位の時間制限
        if hasattr(self, '_page_dl_start') and time.time() - self._page_dl_start > self._PAGE_RESOURCE_TIMEOUT:
            return None

        # 既にDL済みならファイル名だけ返す
        cache_key = (url, page_dir)
        if cache_key in self._fetched_resources:
            return self._fetched_resources[cache_key]

        # 1ページあたりのリソース数上限
        self._page_resource_count = getattr(self, '_page_resource_count', {})
        if self._page_resource_count.get(page_dir, 0) >= self._MAX_RESOURCES_PER_PAGE:
            return None

        try:
            self._limiter.wait()
            resp = java_http.get(url, headers=self._headers, timeout=_RESOURCE_TIMEOUT)
            if resp.status_code in _BACKOFF_CODES:
                self._do_backoff()
                return None
            if resp.status_code != 200:
                return None
        except Exception:
            return None

        filename = self._resource_filename(url)
        filepath = os.path.join(page_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(resp.content)

        self._fetched_resources[cache_key] = filename
        self._page_resource_count[page_dir] = self._page_resource_count.get(page_dir, 0) + 1
        return filename

    _PAGE_RESOURCE_TIMEOUT = 8  # 1ページあたりリソースDLの最大秒数

    def _bg_rewrite(self, html_text, url, page_dir):
        """バックグラウンドでリソースDL + HTML書き換え"""
        def _work():
            try:
                self._prefetch_resources(html_text, url, page_dir)
                rewritten, _ = self._rewrite_html(html_text, url, page_dir)
                with open(os.path.join(page_dir, 'index.html'), 'w', encoding='utf-8') as f:
                    f.write(rewritten)
            except Exception:
                pass  # HTMLは既に保存済みなので失敗しても問題なし
        future = self._bg_pool.submit(_work)
        self._bg_futures.append(future)

    def _wait_bg(self):
        """バックグラウンドリソースDLの完了を待つ"""
        for f in self._bg_futures:
            try:
                f.result(timeout=30)
            except Exception:
                pass
        self._bg_futures.clear()
        self._bg_pool.shutdown(wait=False)

    def _prefetch_resources(self, html_text, base_url, page_dir):
        """HTMLからリソースURLを抽出し、並列でDLしてキャッシュに入れる"""
        urls = set()
        # img src
        for m in re.finditer(r'<(?:img|amp-img)\s[^>]*?src=["\']([^"\']+)["\']', html_text, re.IGNORECASE):
            src = m.group(1)
            if not src.startswith('data:'):
                urls.add(urljoin(base_url, src))
        # link stylesheet href
        for m in re.finditer(r'<link\s[^>]*?href=["\']([^"\']+)["\']', html_text, re.IGNORECASE):
            tag = m.group(0)
            if 'stylesheet' in tag.lower() or 'icon' in tag.lower():
                urls.add(urljoin(base_url, m.group(1)))
        # script src — JS除外（閲覧に不要＆容量削減）
        # css url()
        for m in re.finditer(r'url\(([^)]+)\)', html_text):
            raw = m.group(1).strip('\'"')
            if not raw.startswith('data:'):
                urls.add(urljoin(base_url, raw))

        # フィルタ: 広告・スキップ対象を除外
        urls = [u for u in urls if not self._is_ad_resource(u) and not self._is_skip_resource(u)]

        if not urls:
            return

        self._page_dl_start = time.time()

        def _dl(res_url):
            try:
                return self._fetch_resource(res_url, page_dir)
            except Exception:
                return None

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(_dl, urls[:self._MAX_RESOURCES_PER_PAGE]))

    def _rewrite_html(self, html_text, url, page_dir):
        """HTML内のリソース参照をDL＋ローカル相対パスに書き換え。リンクも抽出"""
        links = []
        self._page_dl_start = time.time()

        def replace_resource(match, attr, tag_match):
            """リソースURLをローカルファイル名に置換"""
            src = match
            if src.startswith('data:'):
                return src
            # ページ単位の時間制限チェック
            if time.time() - self._page_dl_start > self._PAGE_RESOURCE_TIMEOUT:
                return src
            abs_url = urljoin(url, src)
            filename = self._fetch_resource(abs_url, page_dir)
            if filename:
                return filename
            return src

        # <img src="..."> と <img srcset="...">
        def replace_img(m):
            tag = m.group(0)
            # src
            def repl_src(sm):
                old = sm.group(1)
                if old.startswith('data:'):
                    return sm.group(0)
                abs_url = urljoin(url, old)
                fname = self._fetch_resource(abs_url, page_dir)
                return f'src="{fname}"' if fname else sm.group(0)
            tag = re.sub(r'src="([^"]*)"', repl_src, tag)
            tag = re.sub(r"src='([^']*)'", repl_src, tag)
            # srcsetは削除（個別画像はsrcで取得済み）
            tag = re.sub(r'srcset="[^"]*"', 'srcset=""', tag)
            tag = re.sub(r"srcset='[^']*'", "srcset=''", tag)
            return tag
        html_text = re.sub(r'<(?:img|amp-img)\s[^>]*?>', replace_img, html_text, flags=re.IGNORECASE | re.DOTALL)

        # <link rel="stylesheet" href="...">
        def replace_css_link(m):
            tag = m.group(0)
            rel = re.search(r'rel=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if not rel or 'stylesheet' not in rel.group(1).lower():
                return tag
            href_m = re.search(r'href=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if not href_m:
                return tag
            old_href = href_m.group(1)
            abs_url = urljoin(url, old_href)
            fname = self._fetch_resource(abs_url, page_dir)
            if fname:
                # CSS内のurl()も書き換え
                css_path = os.path.join(page_dir, fname)
                self._rewrite_css_file(css_path, abs_url, page_dir)
                return tag[:href_m.start(1)] + fname + tag[href_m.end(1):]
            return tag
        html_text = re.sub(r'<link\s[^>]*?>', replace_css_link, html_text, flags=re.IGNORECASE | re.DOTALL)

        # <script src="..."> — JS除外（閲覧に不要＆容量削減）
        html_text = re.sub(r'<script\s[^>]*?src=["\'][^"\']*["\'][^>]*>\s*</script>', '', html_text, flags=re.IGNORECASE | re.DOTALL)

        # <link rel="icon" href="...">
        def replace_favicon(m):
            tag = m.group(0)
            rel = re.search(r'rel=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if not rel or 'icon' not in rel.group(1).lower():
                return tag
            href_m = re.search(r'href=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if not href_m:
                return tag
            old_href = href_m.group(1)
            if old_href.startswith('data:'):
                return tag
            abs_url = urljoin(url, old_href)
            fname = self._fetch_resource(abs_url, page_dir)
            if fname:
                return tag[:href_m.start(1)] + fname + tag[href_m.end(1):]
            return tag
        html_text = re.sub(r'<link\s[^>]*?>', replace_favicon, html_text, flags=re.IGNORECASE | re.DOTALL)

        # <video>タグ除去
        html_text = re.sub(r'<video\b[^>]*>.*?</video>', '', html_text, flags=re.IGNORECASE | re.DOTALL)

        # inline style内のurl()
        def replace_inline_style(m):
            tag = m.group(0)
            style_m = re.search(r'style=["\']([^"\']*)["\']', tag, re.IGNORECASE)
            if not style_m or 'url(' not in style_m.group(1):
                return tag
            new_style = self._rewrite_css_urls(style_m.group(1), url, page_dir)
            return tag[:style_m.start(1)] + new_style + tag[style_m.end(1):]
        html_text = re.sub(r'<[a-z][a-z0-9]*\s[^>]*style=[^>]*>', replace_inline_style, html_text, flags=re.IGNORECASE | re.DOTALL)

        # <style>内のurl()
        def replace_style_block(m):
            return '<style>' + self._rewrite_css_urls(m.group(1), url, page_dir) + '</style>'
        html_text = re.sub(r'<style[^>]*>(.*?)</style>', replace_style_block, html_text, flags=re.IGNORECASE | re.DOTALL)

        # リンク抽出
        for m in re.finditer(r'<a\s[^>]*?href=["\']([^"\']*)["\']', html_text, re.IGNORECASE):
            href = m.group(1)
            if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            abs_url = urljoin(url, href).split('#')[0]
            if self._is_same_domain(abs_url):
                links.append(abs_url)

        return html_text, links

    def _rewrite_css_urls(self, css_text, base_url, page_dir):
        """CSS内のurl()をローカルファイルに置換"""
        def replace_url(m):
            raw = m.group(1).strip('\'"')
            if raw.startswith('data:'):
                return m.group(0)
            abs_url = urljoin(base_url, raw)
            fname = self._fetch_resource(abs_url, page_dir)
            if fname:
                return f'url({fname})'
            return m.group(0)
        return re.sub(r'url\(([^)]+)\)', replace_url, css_text)

    def _rewrite_css_file(self, css_path, css_url, page_dir):
        """保存済みCSSファイル内のurl()を書き換え。文字コードを自動検出"""
        try:
            with open(css_path, 'rb') as f:
                raw = f.read()
            charset = self._detect_css_charset(raw)
            css_text = raw.decode(charset, errors='replace')
            # @charset宣言をUTF-8に書き換え
            css_text = re.sub(
                r'@charset\s+["\'][a-zA-Z0-9_-]+["\']',
                '@charset "utf-8"', css_text, flags=re.IGNORECASE)
            new_css = self._rewrite_css_urls(css_text, css_url, page_dir)
            # 常にUTF-8で保存し直す（EUC-JP等のCSSもUTF-8に統一）
            with open(css_path, 'w', encoding='utf-8') as f:
                f.write(new_css)
        except Exception:
            pass

    def _detect_css_charset(self, raw_bytes):
        """CSSバイト列からcharsetを検出。HTMLページのcharsetもフォールバックで使う"""
        # @charset宣言を探す
        m = re.search(rb'@charset\s+["\']([a-zA-Z0-9_-]+)["\']', raw_bytes[:256])
        if m:
            return m.group(1).decode('ascii', errors='ignore')
        # HTMLページと同じcharsetを使う（同じサイトならHTMLと同じ文字コードの可能性が高い）
        if hasattr(self, '_page_charset'):
            return self._page_charset
        return 'utf-8'

    def _prescan_existing(self, visited, queue):
        """既存ページを一括スキャン: visitedに入れつつ新リンクをキューに追加"""
        if not os.path.exists(self.cache_dir):
            return

        # cache_dir内の全ディレクトリを走査
        existing_pages = []
        for root, dirs, files in os.walk(self.cache_dir):
            if 'index.html' in files:
                existing_pages.append(root)

        self.page_count = len(existing_pages)
        self._log(f"  既存 {self.page_count} ページを一括スキャン中...")

        all_links = set()
        scanned = 0
        for page_dir in existing_pages:
            if self._stopped:
                break
            index_path = os.path.join(page_dir, 'index.html')
            try:
                with open(index_path, 'r', encoding='utf-8', errors='replace') as f:
                    html = f.read()
                # このページ自体のURLをvisitedに追加（逆引き）
                # page_dirからURLを復元
                rel = os.path.relpath(page_dir, self.cache_dir)
                if rel == '_root':
                    page_url = f'https://{self.domain}/'
                else:
                    page_url = f'https://{self.domain}/{rel}'
                    # .html拡張子が省略されている可能性があるので両方visited
                    visited.add(page_url)
                    visited.add(page_url + '.html')
                    visited.add(page_url + '/')
                visited.add(page_url)

                for m in re.finditer(r'<a\s[^>]*?href=["\']([^"\']*)["\']', html, re.IGNORECASE):
                    href = m.group(1)
                    if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                        continue
                    abs_url = urljoin(page_url, href).split('#')[0]
                    if self._is_same_domain(abs_url):
                        all_links.add(abs_url)
            except Exception:
                pass
            scanned += 1
            if scanned % 50 == 0:
                self._log(f"  スキャン進捗: {scanned}/{len(existing_pages)}")

        # 既存ページのURL自体もvisitedに
        # 新リンク（visitedにないもの）をキューに追加
        new_count = 0
        for link in all_links:
            if link not in visited:
                queue.append((link, 1))
                new_count += 1

        self._log(f"  スキャン完了: {new_count} 件の新URLを発見")

    def run(self, resume=False):
        self._log(f"\U0001f680 クロール開始: {self.start_url}")
        self._log(f"\U0001f4c2 出力先: {self.cache_dir}")
        depth_str = '無制限' if self.max_depth == 0 else str(self.max_depth)
        self._log(f"\u23f1\ufe0f  遅延: {self.delay}s / 深さ: {depth_str}")
        self._log("(PageDir crawler)")

        self.page_count = 0
        queue = deque([(self.start_url, 0)])
        visited = set()

        if resume:
            # 一括プリスキャン: 既存ページを全て読み、リンクをまとめて抽出
            self._prescan_existing(visited, queue)

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

            page_dir = self._url_to_page_dir(url)

            # HTMLを取得
            try:
                self._limiter.wait()
                resp = java_http.get(url, headers=self._headers, timeout=_SESSION_TIMEOUT)
                if resp.status_code in _BACKOFF_CODES:
                    self._do_backoff()
                    # リトライ: キューの末尾に戻す
                    visited.discard(url)
                    queue.append((url, depth))
                    continue
                if resp.status_code != 200:
                    self._log(f"\r[{self.page_count}] {resp.status_code} {unquote(url)[:70]}")
                    continue
                self._backoff_count = 0  # 成功したらバックオフカウンタリセット
                content_type = resp.headers.get('content-type', '')
                if 'html' not in content_type and not url.endswith('.html'):
                    continue
            except Exception:
                self._log(f"\r[{self.page_count}] ERR {unquote(url)[:60]}")
                continue

            # charset検出
            charset = 'utf-8'
            head = resp.content[:4096].lower()
            m = re.search(rb'charset=["\']?([a-zA-Z0-9_-]+)', head)
            if m:
                charset = m.group(1).decode('ascii', errors='ignore')
            self._page_charset = charset  # CSSのcharset検出フォールバック用
            html_text = resp.content.decode(charset, errors='replace')

            # UTF-8で保存するので、metaタグのcharset宣言をUTF-8に書き換え
            html_text = re.sub(
                r'(<meta\s+charset=["\'])([^"\']+)(["\'])',
                r'\g<1>utf-8\3', html_text, flags=re.IGNORECASE)
            html_text = re.sub(
                r'(content=["\'][^"\']*charset=)([a-zA-Z0-9_-]+)',
                r'\g<1>utf-8', html_text, flags=re.IGNORECASE)

            # リンク抽出（リソースDLの前に行う）
            links = []
            for lm in re.finditer(r'<a\s[^>]*?href=["\']([^"\']*)["\']', html_text, re.IGNORECASE):
                href = lm.group(1)
                if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                    continue
                abs_url = urljoin(url, href).split('#')[0]
                if self._is_same_domain(abs_url):
                    links.append(abs_url)

            # ページディレクトリ作成（同名ファイルが既存の場合は退避）
            if os.path.isfile(page_dir):
                os.rename(page_dir, page_dir + '.bak')
            os.makedirs(page_dir, exist_ok=True)

            # まずHTML保存（リソースDLは後でバックグラウンド処理）
            with open(os.path.join(page_dir, 'index.html'), 'w', encoding='utf-8') as f:
                f.write(html_text)

            self.page_count += 1
            display = unquote(url)
            if len(display) > 75:
                display = display[:72] + '...'
            self._log(f"[{self.page_count}] {display}")

            for link in links:
                if link not in visited:
                    queue.append((link, depth + 1))

            # リソースDLをバックグラウンドで実行（次ページのHTML取得と並行）
            self._bg_rewrite(html_text, url, page_dir)

            time.sleep(self.delay)

        # バックグラウンドリソースDLの完了を待つ
        self._log("リソースDL完了待ち...")
        self._wait_bg()

        if self._stopped:
            self._log(f"\u23f8\ufe0f 手動停止: {self.page_count} 件取得済み")
        else:
            self._log(f"\u2705 完了: {self.page_count} 件取得")

    def get_file_base(self):
        return self.cache_dir
