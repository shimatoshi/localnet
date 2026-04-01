"""Crawler — Python/wgetハイブリッドWebクローラー
Windowsではpure Pythonクローラー、それ以外ではwgetを使用"""

import os
import re
import subprocess
import time
import platform
from urllib.parse import urlparse, urljoin, unquote, quote
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from html.parser import HTMLParser
from config import USER_AGENT, CACHE_BASE, AD_DOMAINS

IS_WINDOWS = platform.system() == 'Windows'


class LinkExtractor(HTMLParser):
    """HTMLからリンクを抽出"""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for name, val in attrs:
                if name == 'href' and val:
                    self.links.append(val)


class WgetCrawler:
    def __init__(self, start_url, max_depth=0, delay=1.0,
                 log=None, exclude=None, on_checkpoint=None):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_depth = max_depth  # 0 = 無制限
        self.delay = delay
        self._log = log or print
        self.exclude = exclude or []
        self.on_checkpoint = on_checkpoint

        self.cache_dir = os.path.join(CACHE_BASE, self.domain)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._process = None
        self._stopped = False
        self.page_count = 0

    def _is_excluded(self, url):
        lower = url.lower()
        if any(ad in lower for ad in AD_DOMAINS):
            return True
        if re.search(r'(ads|tracking|affiliate|pixel|beacon|popup)', lower):
            return True
        for pat in self.exclude:
            if re.search(pat, url):
                return True
        return False

    def _url_to_filepath(self, url):
        """URLからキャッシュ内ファイルパスを生成"""
        parsed = urlparse(url)
        path = unquote(parsed.path).lstrip('/')
        if not path or path.endswith('/'):
            path = path + 'index.html'
        if not os.path.splitext(path)[1]:
            path = path + '.html'
        return os.path.join(self.cache_dir, parsed.netloc, path)

    def run(self, resume=False):
        if IS_WINDOWS:
            self._run_python(resume)
        else:
            self._run_wget(resume)

    # === Pure Pythonクローラー（Windows用） ===

    def _run_python(self, resume=False):
        depth_str = '無制限' if self.max_depth == 0 else str(self.max_depth)
        mode = '再開' if resume else '開始'
        self._log(f"\U0001f680 クロール{mode}: {self.start_url}")
        self._log(f"\U0001f4c2 出力先: {self.cache_dir}")
        self._log(f"\u23f1\ufe0f  遅延: {self.delay}s / 深さ: {depth_str}")
        self._log("(Python crawler)")

        self.page_count = 0
        self._stopped = False

        # BFS キュー: (url, depth)
        queue = [(self.start_url, 0)]
        visited = set()

        # 再開時: 既存ファイルのURLをvisitedに追加 & カウント
        if resume:
            base = os.path.join(self.cache_dir, self.domain)
            if os.path.exists(base):
                existing = 0
                for root, dirs, files in os.walk(base):
                    existing += len(files)
                self.page_count = existing
                self._log(f"  既存 {existing} ファイル検出済み、新規のみ取得")

        while queue and not self._stopped:
            url, depth = queue.pop(0)

            # フラグメント除去
            url = url.split('#')[0]
            if not url or url in visited:
                continue
            visited.add(url)

            # ドメインチェック
            parsed = urlparse(url)
            if parsed.netloc != self.domain:
                continue

            # 除外チェック
            if self._is_excluded(url):
                continue

            # 深さチェック
            if self.max_depth > 0 and depth > self.max_depth:
                continue

            # ダウンロード
            filepath = self._url_to_filepath(url)
            if resume and os.path.exists(filepath):
                # 既存ファイルからリンク抽出だけ行う
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                    if b'<html' in content[:1000].lower() or b'<!doctype' in content[:1000].lower():
                        html = content.decode('utf-8', errors='replace')
                        new_links = self._extract_links(html, url)
                        for link in new_links:
                            if link not in visited:
                                queue.append((link, depth + 1))
                except Exception:
                    pass
                continue

            try:
                req = Request(url, headers={'User-Agent': USER_AGENT})
                resp = urlopen(req, timeout=15)
                content = resp.read()
                content_type = resp.headers.get('Content-Type', '')
            except HTTPError as e:
                self._log(f"\r[{self.page_count}] {e.code} {unquote(url)[:70]}")
                continue
            except (URLError, Exception) as e:
                self._log(f"\r[{self.page_count}] ERR {unquote(url)[:60]}")
                continue

            # ファイル保存
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(content)

            self.page_count += 1
            display = unquote(url)
            if len(display) > 75:
                display = display[:72] + '...'
            self._log(f"[{self.page_count}] {display}")

            # HTMLならリンク抽出
            if 'html' in content_type or filepath.endswith('.html'):
                try:
                    html = content.decode('utf-8', errors='replace')
                    new_links = self._extract_links(html, url)
                    for link in new_links:
                        if link not in visited:
                            queue.append((link, depth + 1))
                except Exception:
                    pass

            # チェックポイント
            if self.on_checkpoint and self.page_count > 0 and self.page_count % 500 == 0:
                self._log(f"\U0001f4be チェックポイント: {self.page_count} 件")
                try:
                    self.on_checkpoint(self.domain, self.page_count)
                except Exception as e:
                    self._log(f"\u26a0\ufe0f チェックポイントエラー: {e}")

            # 遅延
            time.sleep(self.delay)

        if self._stopped:
            self._log(f"\u23f8\ufe0f 手動停止: {self.page_count} 件取得済み")
        else:
            self._log(f"\u2705 完了: {self.page_count} 件取得")

    def _extract_links(self, html, base_url):
        """HTMLからリンクを抽出して絶対URLに変換"""
        parser = LinkExtractor()
        try:
            parser.feed(html)
        except Exception:
            pass

        links = []
        for href in parser.links:
            if href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                continue
            abs_url = urljoin(base_url, href).split('#')[0]
            if urlparse(abs_url).netloc == self.domain:
                links.append(abs_url)
        return links

    # === wgetクローラー（Linux/macOS用） ===

    def _build_wget_args(self, resume=False):
        level = 'inf' if self.max_depth == 0 else str(self.max_depth)
        args = [
            'wget',
            '--recursive',
            f'--level={level}',
            '--page-requisites',
            '--adjust-extension',
            '--convert-links',
            f'--wait={self.delay}',
            '--random-wait',
            f'--domains={self.domain}',
            '--span-hosts',
            f'--user-agent={USER_AGENT}',
            '--no-check-certificate',
            f'--directory-prefix={self.cache_dir}',
            '--no-verbose',
            '--show-progress',
            '--tries=3',
            '--timeout=15',
            '--limit-rate=500k',
            '--reject-regex', r'.*(ads|tracking|affiliate|pixel|beacon|popup).*',
        ]

        if resume:
            args.append('--no-clobber')

        reject_domains = ','.join(AD_DOMAINS)
        if reject_domains:
            args.extend(['--exclude-domains', reject_domains])

        for pat in self.exclude:
            args.extend(['--reject-regex', pat])

        args.append(self.start_url)
        return args

    def _run_wget(self, resume=False):
        args = self._build_wget_args(resume=resume)
        depth_str = '無制限' if self.max_depth == 0 else str(self.max_depth)
        mode = '再開' if resume else '開始'
        self._log(f"\U0001f680 クロール{mode}: {self.start_url}")
        self._log(f"\U0001f4c2 出力先: {self.cache_dir}")
        self._log(f"\u23f1\ufe0f  遅延: {self.delay}s / 深さ: {depth_str}")

        self.page_count = 0
        self._stopped = False

        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in self._process.stdout:
                if self._stopped:
                    break
                line = line.rstrip('\n')
                if not line:
                    continue

                if 'saved' in line.lower() or 'saving to' in line.lower():
                    self.page_count += 1
                    self._log(f"[{self.page_count}] {line.strip()}")
                    if self.on_checkpoint and self.page_count % 500 == 0:
                        self._log(f"\U0001f4be チェックポイント: {self.page_count} 件")
                        try:
                            self.on_checkpoint(self.domain, self.page_count)
                        except Exception as e:
                            self._log(f"\u26a0\ufe0f チェックポイントエラー: {e}")
                elif line.startswith('--') or 'http' in line.lower():
                    url_match = re.search(r'(https?://\S+)', line)
                    if url_match:
                        self.page_count += 1
                        url = url_match.group(1)
                        display = unquote(url)
                        if len(display) > 80:
                            display = display[:77] + '...'
                        self._log(f"\r[{self.page_count}] {display}")
                elif '%' in line:
                    self._log(f"\r{line.strip()}")

            self._process.wait()
            exit_code = self._process.returncode

            if self._stopped:
                self._log(f"\u23f8\ufe0f 手動停止: {self.page_count} 件取得済み")
            elif exit_code in (0, 8):
                self._log(f"\u2705 完了 (exit={exit_code}): {self.page_count} 件取得")
            elif exit_code == 6:
                self._log(f"\u26a0\ufe0f 認証が必要 (exit=6)")
            else:
                self._log(f"\u26a0\ufe0f 終了 (exit={exit_code}): {self.page_count} 件取得")

        except Exception as e:
            self._log(f"\u274c エラー: {e}")
            return
        finally:
            self._process = None

    def stop(self):
        self._stopped = True
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except Exception:
                self._process.kill()

    def get_file_base(self):
        base = os.path.join(self.cache_dir, self.domain)
        if not os.path.exists(base):
            base = self.cache_dir
        return base
