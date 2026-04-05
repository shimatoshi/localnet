"""共有定数"""

import os

USER_AGENT = ("Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/136.0.0.0 Mobile Safari/537.36")

# APK版ではserver_launcherが環境変数を設定する
_BASE_DIR = os.environ.get('LOCALNET_BASE', os.path.dirname(os.path.abspath(__file__)))
CACHE_BASE = os.path.join(_BASE_DIR, "cache")
SITES_BASE = os.path.join(_BASE_DIR, "sites")
PORT = int(os.environ.get('LOCALNET_PORT', '8789'))

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
