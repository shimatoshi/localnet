"""HTTPクライアント — curl_cffiベース。
TLSフィンガープリントをChrome相当に偽装し、
プロキシローテーションでIP分散を行う。"""

import threading
import time

from curl_cffi import requests as cffi_requests

# 検証済み生存プロキシ（固定リスト）
_DEFAULT_PROXIES = [
    "http://116.80.82.92:7777",
    "http://116.80.65.81:3172",
    "http://116.80.63.67:7777",
    "http://167.103.34.108:8800",
    "http://167.103.115.102:8800",
    "http://147.161.210.140:8800",
    "http://116.80.49.168:3172",
]

_proxy_list = list(_DEFAULT_PROXIES)
_proxy_lock = threading.Lock()
_proxy_index = 0

_local = threading.local()


def _get_session():
    if not hasattr(_local, 'session'):
        _local.session = cffi_requests.Session(impersonate="chrome")
    return _local.session


class JavaHttpResponse:
    def __init__(self, status_code, content, headers):
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def decode_content(self, charset='utf-8'):
        return self.content.decode(charset, errors='replace')


def is_available():
    return True


def set_proxies(proxy_list):
    global _proxy_list
    with _proxy_lock:
        _proxy_list = list(proxy_list)


def get_proxy_count():
    with _proxy_lock:
        return len(_proxy_list)


def _pick_proxy():
    global _proxy_index
    with _proxy_lock:
        if not _proxy_list:
            return None
        proxy = _proxy_list[_proxy_index % len(_proxy_list)]
        _proxy_index += 1
        return proxy


def remove_proxy(proxy_url):
    with _proxy_lock:
        if proxy_url in _proxy_list:
            _proxy_list.remove(proxy_url)


def get(url, headers=None, timeout=15, _retries=2):
    """HTTP GETを実行。プロキシ失敗→別プロキシ→全滅なら直接。"""
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
            if _retries > 0 and get_proxy_count() > 0:
                return get(url, headers=headers, timeout=timeout, _retries=_retries - 1)
            kwargs.pop("proxies", None)
            resp = session.get(url, **kwargs)
        else:
            raise

    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return JavaHttpResponse(resp.status_code, resp.content, hdrs)
