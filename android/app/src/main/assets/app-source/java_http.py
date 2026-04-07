"""HTTPクライアント — requestsベース。
buildozer版ではpython-for-androidの新しいOpenSSLが使われるため、
Cloudflare等のTLSフィンガープリント検知に引っかからない。"""

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class JavaHttpResponse:
    """requests.Responseの最小互換オブジェクト"""

    def __init__(self, status_code, content, headers):
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def decode_content(self, charset='utf-8'):
        return self.content.decode(charset, errors='replace')


def is_available():
    return True


def get(url, headers=None, timeout=15):
    """HTTP GETを実行してJavaHttpResponseを返す。"""
    resp = requests.get(url, headers=headers, timeout=timeout, verify=False)
    hdrs = {k.lower(): v for k, v in resp.headers.items()}
    return JavaHttpResponse(resp.status_code, resp.content, hdrs)
