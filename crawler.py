"""WgetCrawler — wget を使った無制限再帰Webクローラー"""

import os
import re
import subprocess
import mimetypes

from urllib.parse import urlparse, unquote, quote
import platform
from config import USER_AGENT, CACHE_BASE, AD_DOMAINS

IS_WINDOWS = platform.system() == 'Windows'


class WgetCrawler:
    def __init__(self, start_url, max_depth=0, delay=1.0,
                 log=None, exclude=None, on_checkpoint=None):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_depth = max_depth  # 0 = 無制限
        self.delay = delay
        self._log = log or print
        self.exclude = exclude or []
        self.on_checkpoint = on_checkpoint  # N件ごとに呼ばれるコールバック

        self.cache_dir = os.path.join(CACHE_BASE, self.domain)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._process = None
        self._stopped = False
        self.page_count = 0

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
            '--reject-regex', r'.*(ads|tracking|affiliate|pixel|beacon|popup).*',
        ]

        if resume:
            args.append('--no-clobber')  # 既存ファイルスキップ

        reject_domains = ','.join(AD_DOMAINS)
        if reject_domains:
            args.extend(['--exclude-domains', reject_domains])

        for pat in self.exclude:
            args.extend(['--reject-regex', pat])

        # Windows: URLをデコードして渡す（Windows版wgetがパーセントエンコードを二重変換するため）
        url = self.start_url
        if IS_WINDOWS:
            url = unquote(url)
        args.append(url)
        return args

    def run(self, resume=False):
        args = self._build_wget_args(resume=resume)
        depth_str = '無制限' if self.max_depth == 0 else str(self.max_depth)
        mode = '再開' if resume else '開始'
        self._log(f"\U0001f680 クロール{mode}: {self.start_url}")
        self._log(f"\U0001f4c2 出力先: {self.cache_dir}")
        self._log(f"\u23f1\ufe0f  遅延: {self.delay}s / 深さ: {depth_str}")

        self.page_count = 0
        self._stopped = False

        # Windows: UTF-8環境を強制
        env = os.environ.copy()
        if os.name == 'nt':
            env['PYTHONIOENCODING'] = 'utf-8'

        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                encoding='utf-8',
                errors='replace',
                env=env,
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
                    # チェックポイント
                    if self.on_checkpoint and self.page_count % 500 == 0:
                        self._log(f"\U0001f4be チェックポイント: {self.page_count} 件取得済み、データセット構築中...")
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
        """クロールを停止"""
        self._stopped = True
        if self._process:
            self._process.terminate()

    def get_file_base(self):
        base = os.path.join(self.cache_dir, self.domain)
        if not os.path.exists(base):
            base = self.cache_dir
        return base
