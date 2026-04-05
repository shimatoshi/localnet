package net.localnet.app;

import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * WebViewのfetch()でHTMLを取得し、CSS/画像をインライン化してSingleFileにするクローラー。
 * about:blank上でfetch()を実行するため、ページをレンダリングしない。
 * WebView(Chrome)のTLSスタックを使うのでCloudflare等に弾かれない。
 */
public class CrawlerWebViewManager {

    private static final String TAG = "CrawlerWV";
    private static final int PORT = 8789;

    private final WebView webView;
    private final Handler mainHandler;
    private volatile boolean running = false;
    private volatile boolean fetchInProgress = false;

    public CrawlerWebViewManager(WebView webView) {
        this.webView = webView;
        this.mainHandler = new Handler(Looper.getMainLooper());

        mainHandler.post(() -> {
            WebSettings settings = webView.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setBlockNetworkImage(true);
            settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
            settings.setAllowUniversalAccessFromFileURLs(true);
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
            webView.addJavascriptInterface(new FetchBridge(), "CrawlerBridge");
            // ローカルサーバーをオリジンにしてCORS回避
            webView.loadUrl("http://127.0.0.1:" + PORT + "/api/version");
        });
    }

    public void start() {
        if (running) return;
        running = true;
        new Thread(this::pollLoop, "wv-crawler-poll").start();
    }

    public void stop() {
        running = false;
        fetchInProgress = false;
    }

    private void pollLoop() {
        while (running) {
            try {
                if (fetchInProgress) {
                    Thread.sleep(200);
                    continue;
                }
                String[] result = fetchNextUrl();
                String nextUrl = result[0];
                boolean done = "true".equals(result[1]);

                if (nextUrl != null && !nextUrl.isEmpty()) {
                    fetchInProgress = true;
                    mainHandler.post(() -> runSingleFile(nextUrl));
                    long timeout = System.currentTimeMillis() + 60000; // 60秒（リソース取得含む）
                    while (fetchInProgress && running && System.currentTimeMillis() < timeout) {
                        Thread.sleep(200);
                    }
                    if (fetchInProgress) {
                        fetchInProgress = false;
                        postError(nextUrl, "timeout");
                    }
                } else {
                    Thread.sleep(done ? 2000 : 1000);
                }
            } catch (InterruptedException e) {
                break;
            } catch (Exception e) {
                try { Thread.sleep(2000); } catch (InterruptedException ie) { break; }
            }
        }
    }

    /**
     * fetch()でHTML取得 → パースしてリソースURL抽出 → 各リソースをfetch → インライン化
     * 全部JS内で完結。完成したHTMLをBase64でブリッジに返す。
     */
    private void runSingleFile(String pageUrl) {
        String js = "(async function() {\n" +
            "var pageUrl = '" + escapeJs(pageUrl) + "';\n" +
            "try {\n" +
            // 1. HTML取得
            "  var resp = await fetch(pageUrl, {credentials:'include', headers:{'Accept':'text/html,*/*'}});\n" +
            "  if (resp.status !== 200) { CrawlerBridge.onError(pageUrl, 'HTTP ' + resp.status); return; }\n" +
            "  var html = await resp.text();\n" +
            // DOMParserでパース
            "  var doc = new DOMParser().parseFromString(html, 'text/html');\n" +
            "\n" +
            // ヘルパー: URLをfetchしてdata URIにする
            "  async function toDataUri(url) {\n" +
            "    try {\n" +
            "      var r = await fetch(url);\n" +
            "      if (!r.ok) return null;\n" +
            "      var blob = await r.blob();\n" +
            "      return await new Promise(function(res) {\n" +
            "        var fr = new FileReader();\n" +
            "        fr.onload = function() { res(fr.result); };\n" +
            "        fr.readAsDataURL(blob);\n" +
            "      });\n" +
            "    } catch(e) { return null; }\n" +
            "  }\n" +
            "\n" +
            // ヘルパー: 相対URLを絶対URLにする
            "  function absUrl(base, rel) {\n" +
            "    try { return new URL(rel, base).href; } catch(e) { return rel; }\n" +
            "  }\n" +
            "\n" +
            // 2. CSS: <link rel=stylesheet> → <style>
            "  var links = doc.querySelectorAll('link[rel*=\"stylesheet\"]');\n" +
            "  for (var i = 0; i < links.length; i++) {\n" +
            "    var href = links[i].getAttribute('href');\n" +
            "    if (!href) continue;\n" +
            "    href = absUrl(pageUrl, href);\n" +
            "    try {\n" +
            "      var cr = await fetch(href);\n" +
            "      if (!cr.ok) continue;\n" +
            "      var css = await cr.text();\n" +
            // CSS内のurl()もインライン化
            "      var urlMatches = css.match(/url\\([^)]+\\)/g) || [];\n" +
            "      for (var j = 0; j < urlMatches.length; j++) {\n" +
            "        var raw = urlMatches[j].replace(/url\\(['\"]?/, '').replace(/['\"]?\\)/, '');\n" +
            "        if (raw.startsWith('data:')) continue;\n" +
            "        var du = await toDataUri(absUrl(href, raw));\n" +
            "        if (du) css = css.split(urlMatches[j]).join('url(' + du + ')');\n" +
            "      }\n" +
            "      var style = doc.createElement('style');\n" +
            "      style.textContent = css;\n" +
            "      links[i].replaceWith(style);\n" +
            "    } catch(e) {}\n" +
            "  }\n" +
            "\n" +
            // 3. 画像: src → data URI
            "  var imgs = doc.querySelectorAll('img[src]');\n" +
            "  for (var i = 0; i < imgs.length; i++) {\n" +
            "    var src = imgs[i].getAttribute('src');\n" +
            "    if (!src || src.startsWith('data:')) continue;\n" +
            "    var du = await toDataUri(absUrl(pageUrl, src));\n" +
            "    if (du) imgs[i].setAttribute('src', du);\n" +
            "    imgs[i].removeAttribute('srcset');\n" +
            "  }\n" +
            "\n" +
            // 4. style属性内のurl()
            "  var styled = doc.querySelectorAll('[style]');\n" +
            "  for (var i = 0; i < styled.length; i++) {\n" +
            "    var sv = styled[i].getAttribute('style');\n" +
            "    if (sv.indexOf('url(') < 0) continue;\n" +
            "    var um = sv.match(/url\\([^)]+\\)/g) || [];\n" +
            "    for (var j = 0; j < um.length; j++) {\n" +
            "      var raw = um[j].replace(/url\\(['\"]?/, '').replace(/['\"]?\\)/, '');\n" +
            "      if (raw.startsWith('data:')) continue;\n" +
            "      var du = await toDataUri(absUrl(pageUrl, raw));\n" +
            "      if (du) sv = sv.split(um[j]).join('url(' + du + ')');\n" +
            "    }\n" +
            "    styled[i].setAttribute('style', sv);\n" +
            "  }\n" +
            "\n" +
            // 5. 完成HTMLをBase64でブリッジに返す
            "  var finalHtml = '<!DOCTYPE html>' + doc.documentElement.outerHTML;\n" +
            "  var b64 = btoa(unescape(encodeURIComponent(finalHtml)));\n" +
            "  CrawlerBridge.onSuccess(pageUrl, b64);\n" +
            "} catch(e) {\n" +
            "  CrawlerBridge.onError(pageUrl, e.toString());\n" +
            "}\n" +
            "})();";
        webView.evaluateJavascript(js, null);
    }

    private class FetchBridge {
        @JavascriptInterface
        public void onSuccess(String pageUrl, String htmlB64) {
            new Thread(() -> {
                try {
                    byte[] bytes = Base64.decode(htmlB64, Base64.DEFAULT);
                    String html = new String(bytes, StandardCharsets.UTF_8);
                    postResult(pageUrl, html);
                } catch (Exception e) {
                    postError(pageUrl, "decode: " + e.getMessage());
                }
                fetchInProgress = false;
            }).start();
        }

        @JavascriptInterface
        public void onError(String pageUrl, String error) {
            new Thread(() -> {
                postError(pageUrl, error);
                fetchInProgress = false;
            }).start();
        }
    }

    // === サーバー通信 ===

    private String[] fetchNextUrl() {
        try {
            URL url = new URL("http://127.0.0.1:" + PORT + "/api/webview-crawl/next");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(3000);
            conn.setReadTimeout(3000);
            if (conn.getResponseCode() == 200) {
                String json = readStream(conn.getInputStream());
                conn.disconnect();
                return new String[] { extractJsonString(json, "url"), extractJsonValue(json, "done") };
            }
            conn.disconnect();
        } catch (Exception e) {}
        return new String[] { null, "false" };
    }

    private void postResult(String pageUrl, String html) {
        try {
            URL url = new URL("http://127.0.0.1:" + PORT + "/api/webview-crawl/result");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setDoOutput(true);
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(30000);

            String htmlB64 = Base64.encodeToString(
                html.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
            String body = "{\"url\":\"" + escapeJson(pageUrl) + "\",\"html_b64\":\"" + htmlB64 + "\"}";

            byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
            conn.setFixedLengthStreamingMode(bodyBytes.length);
            OutputStream os = conn.getOutputStream();
            os.write(bodyBytes);
            os.flush();
            os.close();
            conn.getResponseCode();
            conn.disconnect();
        } catch (Exception e) {
            Log.e(TAG, "postResult error", e);
        }
    }

    private void postError(String pageUrl, String error) {
        try {
            URL url = new URL("http://127.0.0.1:" + PORT + "/api/webview-crawl/result");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            conn.setDoOutput(true);
            String body = "{\"url\":\"" + escapeJson(pageUrl) + "\",\"error\":\"" + escapeJson(error) + "\"}";
            OutputStream os = conn.getOutputStream();
            os.write(body.getBytes(StandardCharsets.UTF_8));
            os.flush();
            os.close();
            conn.getResponseCode();
            conn.disconnect();
        } catch (Exception e) {}
    }

    // === ユーティリティ ===

    private String readStream(InputStream is) throws Exception {
        ByteArrayOutputStream baos = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int len;
        while ((len = is.read(buf)) != -1) baos.write(buf, 0, len);
        return baos.toString("UTF-8");
    }

    private String extractJsonString(String json, String key) {
        String search = "\"" + key + "\"";
        int idx = json.indexOf(search);
        if (idx < 0) return null;
        int colon = json.indexOf(":", idx + search.length());
        if (colon < 0) return null;
        String rest = json.substring(colon + 1).trim();
        if (rest.startsWith("null")) return null;
        if (rest.startsWith("\"")) {
            int start = 1;
            int end = rest.indexOf("\"", start);
            while (end > 0 && rest.charAt(end - 1) == '\\') end = rest.indexOf("\"", end + 1);
            return end > 0 ? rest.substring(start, end) : null;
        }
        return null;
    }

    private String extractJsonValue(String json, String key) {
        String search = "\"" + key + "\"";
        int idx = json.indexOf(search);
        if (idx < 0) return null;
        int colon = json.indexOf(":", idx + search.length());
        if (colon < 0) return null;
        String rest = json.substring(colon + 1).trim();
        StringBuilder sb = new StringBuilder();
        for (char c : rest.toCharArray()) {
            if (c == ',' || c == '}' || c == ']') break;
            if (c != ' ' && c != '"') sb.append(c);
        }
        return sb.toString();
    }

    private String escapeJson(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"")
                .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t");
    }

    private String escapeJs(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("'", "\\'")
                .replace("\n", "\\n").replace("\r", "\\r");
    }
}
