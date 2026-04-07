"""JavaのHttpURLConnectionをChaquopyブリッジ経由で使うHTTPクライアント。
AndroidのTLSスタック（BoringSSL）を使うため、Chaquopy同梱のOpenSSLに縛られない。"""

try:
    from java.net import URL, HttpURLConnection
    from java.io import BufferedInputStream, ByteArrayOutputStream
    from javax.net.ssl import HttpsURLConnection
    _JAVA_AVAILABLE = True
except ImportError:
    _JAVA_AVAILABLE = False


class JavaHttpResponse:
    """requests.Responseの最小互換オブジェクト"""

    def __init__(self, status_code, content, headers):
        self.status_code = status_code
        self.content = content
        self.headers = headers

    def decode_content(self, charset='utf-8'):
        return self.content.decode(charset, errors='replace')


def is_available():
    return _JAVA_AVAILABLE


def get(url, headers=None, timeout=15):
    """HTTP GETを実行してJavaHttpResponseを返す。
    timeout: 秒単位（Java側はミリ秒に変換）"""
    if not _JAVA_AVAILABLE:
        raise RuntimeError("Java bridge not available (not running in Chaquopy)")

    conn = None
    try:
        java_url = URL(url)
        conn = java_url.openConnection()

        timeout_ms = int(timeout * 1000)
        conn.setConnectTimeout(timeout_ms)
        conn.setReadTimeout(timeout_ms)
        conn.setInstanceFollowRedirects(True)
        conn.setRequestMethod("GET")

        if headers:
            for key, value in headers.items():
                conn.setRequestProperty(key, value)

        status = conn.getResponseCode()

        # レスポンスヘッダー取得
        resp_headers = {}
        i = 0
        while True:
            key = conn.getHeaderFieldKey(i)
            val = conn.getHeaderField(i)
            if val is None:
                break
            if key is not None:
                resp_headers[key.lower()] = val
            i += 1

        # ボディ読み取り
        try:
            stream = BufferedInputStream(conn.getInputStream())
        except Exception:
            stream = BufferedInputStream(conn.getErrorStream()) if conn.getErrorStream() else None

        content = b''
        if stream:
            baos = ByteArrayOutputStream()
            buf = bytearray(8192)
            while True:
                n = stream.read(buf)
                if n == -1:
                    break
                baos.write(buf, 0, n)
            stream.close()
            content = bytes(baos.toByteArray())
            baos.close()

        return JavaHttpResponse(status, content, resp_headers)

    finally:
        if conn is not None:
            conn.disconnect()
