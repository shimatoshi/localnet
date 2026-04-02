"""共有定数"""

import os

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
CACHE_BASE = os.path.join(_BASE_DIR, "cache")
DATASETS_DIR = os.path.join(_BASE_DIR, "datasets")
PORT = 8789

# 広告・トラッキング系ドメイン
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
