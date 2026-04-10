"""共有定数"""

import os
import random

USER_AGENT = ("Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/136.0.0.0 Mobile Safari/537.36")

# ブラウザプロファイル群（UA + ヘッダーの整合性を保つ）
BROWSER_PROFILES = [
    {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Mobile Safari/537.36',
        'Sec-Ch-Ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?1',
        'Sec-Ch-Ua-Platform': '"Android"',
    },
    {
        'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Mobile/15E148 Safari/604.1',
        'Sec-Ch-Ua': '',
        'Sec-Ch-Ua-Mobile': '?1',
        'Sec-Ch-Ua-Platform': '"iOS"',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        'Sec-Ch-Ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36',
        'Sec-Ch-Ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"macOS"',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:137.0) Gecko/20100101 Firefox/137.0',
        'Sec-Ch-Ua': '',
        'Sec-Ch-Ua-Mobile': '',
        'Sec-Ch-Ua-Platform': '',
    },
    {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.4 Safari/605.1.15',
        'Sec-Ch-Ua': '',
        'Sec-Ch-Ua-Mobile': '',
        'Sec-Ch-Ua-Platform': '',
    },
]


def random_profile():
    """ランダムなブラウザプロファイルを返す"""
    return random.choice(BROWSER_PROFILES)

# APK版ではserver_launcherが環境変数を設定する
_BASE_DIR = os.environ.get('LOCALNET_BASE', os.path.dirname(os.path.abspath(__file__)))
CACHE_BASE = os.path.join(_BASE_DIR, "cache")
SITES_BASE = os.path.join(_BASE_DIR, "sites")
PORT = int(os.environ.get('LOCALNET_PORT', '8789'))
DEV_MODE = os.environ.get('LOCALNET_DEV', '').lower() in ('1', 'true', 'yes')

AD_DOMAINS = [
    'doubleclick.net', 'googlesyndication.com', 'googleadservices.com',
    'google-analytics.com', 'googletagmanager.com', 'googletagservices.com',
    'pagead2.googlesyndication.com', 'adservice.google.com',
    'adnxs.com', 'adsrvr.org', 'adform.net', 'criteo.com', 'criteo.net',
    'outbrain.com', 'taboola.com', 'amazon-adsystem.com',
    'moatads.com', 'openx.net', 'pubmatic.com', 'rubiconproject.com',
    'media.net', 'revcontent.com', 'mgid.com',
    'facebook.net', 'connect.facebook.net', 'platform.twitter.com',
    'analytics.tiktok.com',
    'scorecardresearch.com', 'quantserve.com', 'chartbeat.com',
    'hotjar.com', 'mouseflow.com', 'clarity.ms',
    'newrelic.com', 'nr-data.net', 'segment.io', 'mixpanel.com',
    'amplitude.com', 'fullstory.com', 'optimizely.com',
    'yads.yahoo.co.jp', 'yjtag.yahoo.co.jp',
    'i-mobile.co.jp', 'microad.co.jp', 'impact-ad.jp',
    'a8.net', 'accesstrade.net', 'valuecommerce.com',
    'felmat.net', 'fluct.jp', 'geniee.co.jp',
    'cdn.ampproject.org', 'consent.cookiebot.com', 'cdn.cookielaw.org',
]
