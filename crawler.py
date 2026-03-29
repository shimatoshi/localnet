"""WgetCrawler — wget を使った高速Webサイトクローラー"""

import os
import re
import subprocess
import mimetypes

from urllib.parse import urlparse, unquote, quote
from config import USER_AGENT, CACHE_BASE, AD_DOMAINS


class WgetCrawler:
    def __init__(self, start_url, max_depth=2, delay=1.0, daily_limit=5000,
                 log=None, exclude=None):
        self.start_url = start_url
        self.domain = urlparse(start_url).netloc
        self.max_depth = max_depth
        self.delay = delay
        self.daily_limit = daily_limit
        self._log = log or print
        self.exclude = exclude or []

        self.cache_dir = os.path.join(CACHE_BASE, self.domain)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._process = None

    def _build_wget_args(self):
        args = [
            'wget',
            '--recursive',
            f'--level={self.max_depth}',
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
            f'--quota={self.daily_limit}m',
            '--no-verbose',
            '--show-progress',
            '--tries=3',
            '--timeout=15',
            '--reject-regex', r'.*(ads|tracking|affiliate|pixel|beacon|popup).*',
        ]

        reject_domains = ','.join(AD_DOMAINS)
        if reject_domains:
            args.extend(['--exclude-domains', reject_domains])

        for pat in self.exclude:
            args.extend(['--reject-regex', pat])

        args.append(self.start_url)
        return args

    def run(self):
        args = self._build_wget_args()
        self._log(f"\U0001f680 wget クロール開始: {self.start_url}")
        self._log(f"\U0001f4c2 出力先: {self.cache_dir}")
        self._log(f"\u23f1\ufe0f  遅延: {self.delay}s / 深さ: {self.max_depth}")

        count = 0
        try:
            self._process = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            for line in self._process.stdout:
                line = line.rstrip('\n')
                if not line:
                    continue

                if 'saved' in line.lower() or 'saving to' in line.lower():
                    count += 1
                    self._log(f"[{count}] {line.strip()}")
                elif line.startswith('--') or 'http' in line.lower():
                    url_match = re.search(r'(https?://\S+)', line)
                    if url_match:
                        count += 1
                        url = url_match.group(1)
                        display = unquote(url)
                        if len(display) > 80:
                            display = display[:77] + '...'
                        self._log(f"\r[{count}] {display}")
                elif '%' in line:
                    self._log(f"\r{line.strip()}")

            self._process.wait()
            exit_code = self._process.returncode

            if exit_code in (0, 8):
                self._log(f"\u2705 wget完了 (exit={exit_code})")
            elif exit_code == 6:
                self._log(f"\u26a0\ufe0f 認証が必要です (exit=6)")
            else:
                self._log(f"\u26a0\ufe0f wget終了 (exit={exit_code})")

        except Exception as e:
            self._log(f"\u274c wget実行エラー: {e}")
            return
        finally:
            self._process = None

        self._log(f"\u2705 クロール完了: {count} リクエスト処理")

    def stop(self):
        if self._process:
            self._process.terminate()

    def get_file_base(self):
        """クロール済みファイルのベースディレクトリを返す"""
        base = os.path.join(self.cache_dir, self.domain)
        if not os.path.exists(base):
            base = self.cache_dir
        return base
