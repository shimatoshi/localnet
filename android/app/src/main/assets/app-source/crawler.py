"""PageDirCrawler — 1ページ1フォルダ式クローラー
ページごとにフォルダを作り、HTML・CSS・画像・JSをファイルとして保存。
HTMLの参照は同フォルダ内の相対パスに書き換える。
Base64変換・BS4によるインライン化が不要なため軽量。"""

import os
import re
import time
import random
import hashlib
import mimetypes
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin, unquote

import java_http

from config import USER_AGENT, CACHE_BASE, AD_DOMAINS, random_profile
from compactor import compact_site

_AD_SET = set(AD_DOMAINS)
_SESSION_TIMEOUT = 15
_RESOURCE_TIMEOUT = (1, 2)  # (connect, read) timeout
_SKIP_EXT = {'.gif', '.mp4', '.webm', '.ogv', '.mpeg', '.mov', '.avi', '.js'}
_MAX_RPS = 3  # 秒間リクエスト上限（リソースDL含む全体、個人サーバーにも安全）
_BACKOFF_CODES = {429, 503}  # バックオフ対象ステータス
_BACKOFF_STEPS = [5, 10, 30, 60]  # 段階的バックオフ秒数
_COMPACT_INTERVAL = 500  # N ページごとに圧縮パスを実行


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

        self._base_headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        }
        # 初回プロファイル設定
        self._rotate_profile()
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

    def _rotate_profile(self):
        """ブラウザプロファイルをランダム切り替え"""
        profile = random_profile()
        self._headers = {**self._base_headers, **profile}
        # Sec-Ch-Ua が空のプロファイル（Safari/Firefox）はヘッダー自体を消す
        self._headers = {k: v for k, v in self._headers.items() if v}

    def _make_headers(self, url, from_url=None):
        """リクエスト用ヘッダーを生成（リファラーを自然に）"""
        h = dict(self._headers)
        if from_url:
            # サイト内遷移: 前のページがリファラー
            h['Referer'] = from_url
            h['Sec-Fetch-Site'] = 'same-origin'
        else:
            # 初回アクセス: Google検索から来た体
            h['Referer'] = f'https://www.google.com/search?q={self.domain}'
            h['Sec-Fetch-Site'] = 'cross-site'
        return h

    def _human_delay(self):
        """人間っぽいランダム遅延（基準delay ± 50%）"""
        jitter = self.delay * random.uniform(0.5, 1.5)
        # たまに長めの停止（読んでる風）5%の確率
        if random.random() < 0.05:
            jitter += random.uniform(1.0, 2.0)
        time.sleep(jitter)

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
        host = urlparse(url).netloc.lower()
        if any(ad == host or host.endswith('.' + ad) for ad in _AD_SET):
            return True
        if re.search(r'(^|[./-])(ads|tracking|affiliate|pixel|beacon|popup)([./-]|$)', host):
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

    _ALT_EXTS_FOR_IMAGE = ('.webp', '.jpg', '.jpeg', '.png', '.gif', '.svg')

    def _find_existing_on_disk(self, url, page_dir):
        """前回クロール+compactor済みのファイルが disk にあれば、そのローカル参照を返す。

        compactor が jpg/png を webp に変換したり _shared に退避したりするので、
        ハッシュ一致で元ファイル名とは異なる拡張子/場所にある可能性がある。
        """
        expected = self._resource_filename(url)
        stem, ext = os.path.splitext(expected)
        candidates = [expected]
        # 画像は webp 化されている可能性（compactor phase 2）
        if ext.lower() in ('.jpg', '.jpeg', '.png'):
            for alt in self._ALT_EXTS_FOR_IMAGE:
                if alt != ext.lower():
                    candidates.append(stem + alt)

        # page_dir 内
        if os.path.isdir(page_dir):
            for name in candidates:
                if os.path.isfile(os.path.join(page_dir, name)):
                    return name
        # _shared 内（dedup phase で退避されたもの）
        shared = os.path.join(self.cache_dir, '_shared')
        if os.path.isdir(shared):
            for name in candidates:
                if os.path.isfile(os.path.join(shared, name)):
                    return f'/api/cache/{self.domain}/_shared/{name}'
        return None

    _MAX_RESOURCES_PER_PAGE = 200

    def _fetch_resource(self, url, page_dir):
        """リソースをDLしてpage_dir内に保存。ローカルファイル名を返す"""
        if self._is_ad_resource(url) or self._is_skip_resource(url):
            return None

        # 既にDL済みならファイル名だけ返す（メモリキャッシュ）
        cache_key = (url, page_dir)
        if cache_key in self._fetched_resources:
            return self._fetched_resources[cache_key]

        # disk 上に前回クロール分が残っていれば再利用（再DLも timeout も不要）
        existing = self._find_existing_on_disk(url, page_dir)
        if existing:
            self._fetched_resources[cache_key] = existing
            return existing

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

    def _run_compaction(self):
        """圧縮パス: バックグラウンドDL完了後にフォント排除+画像webp変換"""
        self._log(f"🗜️ 圧縮パス開始 ({self.page_count}ページ到達)")
        # 進行中のリソースDLを先に完了させる
        for f in self._bg_futures:
            try:
                f.result(timeout=30)
            except Exception:
                pass
        self._bg_futures.clear()
        try:
            compact_site(self.domain, log=self._log)
        except Exception as e:
            self._log(f"[compactor] エラー: {e}")
        self._log(f"🗜️ 圧縮パス完了、クロール再開")

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
        # img data-src (lazy loading)
        for m in re.finditer(r'<(?:img|amp-img)\s[^>]*?\bdata-src=["\']([^"\']+)["\']', html_text, re.IGNORECASE):
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

        # <img src="..."> / data-src（lazy load用） / srcset
        def replace_img(m):
            tag = m.group(0)
            def repl_url_attr(sm, attr):
                old = sm.group(1)
                if old.startswith('data:'):
                    return sm.group(0)
                abs_url = urljoin(url, old)
                fname = self._fetch_resource(abs_url, page_dir)
                return f'{attr}="{fname}"' if fname else sm.group(0)
            # src
            tag = re.sub(r'\bsrc="([^"]*)"', lambda sm: repl_url_attr(sm, 'src'), tag)
            tag = re.sub(r"\bsrc='([^']*)'", lambda sm: repl_url_attr(sm, 'src'), tag)
            # data-src / data-lazy-src（lazy loading 属性）
            tag = re.sub(r'\bdata-src="([^"]*)"', lambda sm: repl_url_attr(sm, 'data-src'), tag)
            tag = re.sub(r"\bdata-src='([^']*)'", lambda sm: repl_url_attr(sm, 'data-src'), tag)
            tag = re.sub(r'\bdata-lazy-src="([^"]*)"', lambda sm: repl_url_attr(sm, 'data-lazy-src'), tag)
            # srcsetは削除（個別画像はsrcで取得済み）
            tag = re.sub(r'srcset="[^"]*"', 'srcset=""', tag)
            tag = re.sub(r"srcset='[^']*'", "srcset=''", tag)
            # lazy load: src=data:プレースホルダを data-src のローカル値で上書き
            # （外部 lazyload JS を剥がしてるので data: のままだと表示されない）
            src_m = re.search(r'\bsrc=["\'](data:[^"\']*)["\']', tag)
            if src_m:
                ds_m = re.search(r'\bdata-src=["\']([^"\']+)["\']', tag)
                if ds_m and not ds_m.group(1).startswith('data:'):
                    tag = tag[:src_m.start(1)] + ds_m.group(1) + tag[src_m.end(1):]
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

        # <amp-img> は AMP runtime 無しでは描画されないので <img> に変換
        # （src書換は既に <(?:img|amp-img)> 正規表現で済んでいる）
        html_text = re.sub(r'<amp-img\b', '<img', html_text, flags=re.IGNORECASE)
        html_text = re.sub(r'</amp-img\s*>', '', html_text, flags=re.IGNORECASE)

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

        prev_url = None  # リファラー用: 前のページURL
        pages_since_rotate = 0

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

            # 10〜30ページごとにブラウザプロファイル切り替え
            pages_since_rotate += 1
            if pages_since_rotate >= random.randint(10, 30):
                self._rotate_profile()
                pages_since_rotate = 0

            page_dir = self._url_to_page_dir(url)
            req_headers = self._make_headers(url, from_url=prev_url)

            # HTMLを取得
            try:
                self._limiter.wait()
                resp = java_http.get(url, headers=req_headers, timeout=_SESSION_TIMEOUT)
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

            # 圧縮パス: N ページごとにフォント排除 + 画像webp変換
            if self.page_count % _COMPACT_INTERVAL == 0:
                self._run_compaction()

            for link in links:
                if link not in visited:
                    queue.append((link, depth + 1))

            # リソースDLをバックグラウンドで実行（次ページのHTML取得と並行）
            self._bg_rewrite(html_text, url, page_dir)

            prev_url = url
            self._human_delay()

        # バックグラウンドリソースDLの完了を待つ
        self._log("リソースDL完了待ち...")
        self._wait_bg()

        # 最終圧縮: クロール終了時に必ず実行 (直前のN件きっかけで走った場合は除く)
        # 500件未満で終わったサイトが無圧縮で残らないように保証
        if self.page_count > 0 and self.page_count % _COMPACT_INTERVAL != 0:
            self._run_compaction()

        if self._stopped:
            self._log(f"\u23f8\ufe0f 手動停止: {self.page_count} 件取得済み")
        else:
            self._log(f"\u2705 完了: {self.page_count} 件取得")

    def get_file_base(self):
        return self.cache_dir
