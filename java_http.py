"""HTTPクライアント — curl_cffiベース。
TLSフィンガープリントをChrome相当に偽装し、
プロキシローテーションでIP分散を行う。"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi import requests as cffi_requests

# プロキシリスト
_proxy_list = []
_proxy_lock = threading.Lock()
_proxy_index = 0

# curl_cffiセッション（impersonate付き）
_local = threading.local()

# ProxyScrapeエンドポイント
_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all",
]

# ヘルスチェック設定（Pixel 3a等の低スペック端末でも動くよう軽量に）
_HEALTH_URL = "https://www.google.com/generate_204"  # 超軽量、204返すだけ
_HEALTH_OK_CODES = {200, 204}
_HEALTH_TIMEOUT = 3
_HEALTH_WORKERS = 10
_MAX_CANDIDATES = 150
_MIN_PROXIES = 5


def _get_session():
    """スレッドローカルなcurl_cffiセッションを返す"""
    if not hasattr(_local, 'session'):
        _local.session = cffi_requests.Session(impersonate="chrome")
    return _local.session


class JavaHttpResponse:
    """レスポンスの最小互換オブジェクト"""

    def __init__(self, status_code, content, headers):
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def decode_content(self, charset='utf-8'):
        return self.content.decode(charset, errors='replace')


def is_available():
    return True


def set_proxies(proxy_list):
    """プロキシリストを設定する。各要素は 'http://ip:port' 形式"""
    global _proxy_list
    with _proxy_lock:
        _proxy_list = list(proxy_list)


def get_proxy_count():
    with _proxy_lock:
        return len(_proxy_list)


def _pick_proxy():
    """ラウンドロビンでプロキシを選択。なければNone"""
    global _proxy_index
    with _proxy_lock:
        if not _proxy_list:
            return None
        proxy = _proxy_list[_proxy_index % len(_proxy_list)]
        _proxy_index += 1
        return proxy


def _check_proxy(proxy_url):
    """プロキシが生きてるか確認。生きてたら(proxy_url, 応答時間)を返す"""
    try:
        session = cffi_requests.Session(impersonate="chrome")
        t0 = time.time()
        r = session.get(
            _HEALTH_URL,
            proxies={"https": proxy_url, "http": proxy_url},
            timeout=_HEALTH_TIMEOUT,
            verify=False,
        )
        dt = time.time() - t0
        if r.status_code in _HEALTH_OK_CODES:
            return (proxy_url, dt)
    except Exception:
        pass
    return None


def fetch_and_validate_proxies(log=None):
    """ProxyScrapeからプロキシ取得→並列ヘルスチェック→生存プロキシをセット"""
    _log = log or print

    # 1. プロキシリスト取得
    candidates = []
    session = cffi_requests.Session(impersonate="chrome")
    for src in _PROXY_SOURCES:
        try:
            r = session.get(src, timeout=10)
            lines = [l.strip() for l in r.text.splitlines() if l.strip()]
            candidates.extend(lines)
            _log(f"  プロキシ候補: {len(lines)}個 取得")
        except Exception as e:
            _log(f"  プロキシ取得失敗: {e}")

    if not candidates:
        _log("  プロキシ候補なし、直接アクセスで続行")
        return 0

    # 重複除去+シャッフルして上限まで
    candidates = list(set(candidates))
    import random
    random.shuffle(candidates)
    candidates = candidates[:_MAX_CANDIDATES]
    proxy_urls = [f"http://{c}" for c in candidates]

    # 2. 並列ヘルスチェック
    _log(f"  ヘルスチェック中... ({len(proxy_urls)}個)")
    alive = []
    with ThreadPoolExecutor(max_workers=_HEALTH_WORKERS) as pool:
        futures = {pool.submit(_check_proxy, p): p for p in proxy_urls}
        for f in as_completed(futures):
            result = f.result()
            if result:
                alive.append(result)

    # 応答時間でソート（速い順）
    alive.sort(key=lambda x: x[1])
    good_proxies = [p for p, _ in alive]

    _log(f"  生存プロキシ: {len(good_proxies)}個 (候補{len(proxy_urls)}中)")
    if good_proxies:
        top3 = [(p.replace('http://', ''), f"{t:.1f}s") for p, t in alive[:3]]
        _log(f"  最速3: {top3}")

    set_proxies(good_proxies)
    return len(good_proxies)


_REFRESH_THRESHOLD = 5  # この数以下でプロキシ自動リフレッシュ
_last_refresh = 0.0
_REFRESH_COOLDOWN = 300  # リフレッシュ間の最小間隔（秒）


def remove_proxy(proxy_url):
    """死んだプロキシをリストから除去"""
    with _proxy_lock:
        if proxy_url in _proxy_list:
            _proxy_list.remove(proxy_url)


def _maybe_refresh():
    """プロキシが減りすぎたら自動リフレッシュ"""
    global _last_refresh
    with _proxy_lock:
        count = len(_proxy_list)
    if count <= _REFRESH_THRESHOLD and time.time() - _last_refresh > _REFRESH_COOLDOWN:
        _last_refresh = time.time()
        fetch_and_validate_proxies()


def get(url, headers=None, timeout=15, _retries=2):
    """HTTP GETを実行してJavaHttpResponseを返す。
    プロキシ失敗時は別のプロキシで再試行、全滅なら直接アクセス。"""
    session = _get_session()

    kwargs = {
        "headers": headers,
        "timeout": timeout,
        "verify": False,
    }

    proxy = _pick_proxy()
    if proxy:
        kwargs["proxies"] = {"https": proxy, "http": proxy}

    try:
        resp = session.get(url, **kwargs)
    except Exception:
        if proxy:
            remove_proxy(proxy)
            _maybe_refresh()
            # 別のプロキシで再試行
            if _retries > 0 and get_proxy_count() > 0:
                return get(url, headers=headers, timeout=timeout, _retries=_retries - 1)
            # プロキシ全滅→直接アクセス
            kwargs.pop("proxies", None)
            resp = session.get(url, **kwargs)
        else:
            raise

    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return JavaHttpResponse(resp.status_code, resp.content, hdrs)
