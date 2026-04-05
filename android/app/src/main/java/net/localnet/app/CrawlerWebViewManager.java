package net.localnet.app;

import android.os.Handler;
import android.os.Looper;
import android.util.Base64;
import android.util.Log;
import android.webkit.JavascriptInterface;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * WebViewでページをロード→JS内でCSS/画像をインライン化→SingleFileなHTMLをサーバーに返す。
 * WebView(Chrome)のTLSスタックを使うのでCloudflare等に弾かれない。
 */
public class CrawlerWebViewManager {

    private static final String TAG = "CrawlerWV";
    private static final int PORT = 8789;

    private final WebView webView;
    private final Handler mainHandler;
    private volatile boolean running = false;
    private volatile boolean fetchInProgress = false;
    private volatile String currentUrl = null;

    public CrawlerWebViewManager(WebView webView) {
        this.webView = webView;
        this.mainHandler = new Handler(Looper.getMainLooper());

        mainHandler.post(() -> {
            WebSettings settings = webView.getSettings();
            settings.setJavaScriptEnabled(true);
            settings.setDomStorageEnabled(true);
            settings.setBlockNetworkImage(false);
            settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);

            webView.addJavascriptInterface(new Bridge(), "SingleFileBridge");

            webView.setWebViewClient(new WebViewClient() {
                @Override
                public void onPageFinished(WebView view, String url) {
                    super.onPageFinished(view, url);
                    if (fetchInProgress && url != null && !url.equals("about:blank")) {
                        // ページロード完了後、少し待ってからインライン化実行
                        mainHandler.postDelayed(() -> inlinePage(), 1500);
                    }
                }
            });

            webView.loadUrl("about:blank");
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
                    Thread.sleep(300);
                    continue;
                }
                String[] result = fetchNextUrl();
                String nextUrl = result[0];
                boolean done = "true".equals(result[1]);

                if (nextUrl != null && !nextUrl.isEmpty()) {
                    fetchInProgress = true;
                    currentUrl = nextUrl;
                    mainHandler.post(() -> webView.loadUrl(nextUrl));
                    // タイムアウト待ち
                    long timeout = System.currentTimeMillis() + 30000;
                    while (fetchInProgress && running && System.currentTimeMillis() < timeout) {
                        Thread.sleep(300);
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

    /** ページ内の外部リソースをインライン化するJSを実行 */
    private void inlinePage() {
        String js = "(async function() {" +
            "try {" +
            // CSS: <link rel=stylesheet> → <style>にインライン化
            "  var links = document.querySelectorAll('link[rel*=stylesheet]');" +
            "  for (var i = 0; i < links.length; i++) {" +
            "    try {" +
            "      var href = links[i].href;" +
            "      if (!href) continue;" +
            "      var r = await fetch(href);" +
            "      if (r.ok) {" +
            "        var css = await r.text();" +
            // CSS内のurl()もインライン化
            "        var urls = css.match(/url\\(([^)]+)\\)/g) || [];" +
            "        for (var j = 0; j < urls.length; j++) {" +
            "          var raw = urls[j].replace(/url\\(['\"]?/, '').replace(/['\"]?\\)/, '');" +
            "          if (raw.startsWith('data:')) continue;" +
            "          try {" +
            "            var abs = new URL(raw, href).href;" +
            "            var rr = await fetch(abs);" +
            "            if (rr.ok) {" +
            "              var blob = await rr.blob();" +
            "              var dr = new FileReader();" +
            "              var du = await new Promise(function(res) { dr.onload = function() { res(dr.result); }; dr.readAsDataURL(blob); });" +
            "              css = css.split(raw).join(du);" +
            "            }" +
            "          } catch(e) {}" +
            "        }" +
            "        var s = document.createElement('style');" +
            "        s.textContent = css;" +
            "        links[i].replaceWith(s);" +
            "      }" +
            "    } catch(e) {}" +
            "  }" +
            // 画像: src → data URI
            "  var imgs = document.querySelectorAll('img[src]');" +
            "  for (var i = 0; i < imgs.length; i++) {" +
            "    var src = imgs[i].src;" +
            "    if (!src || src.startsWith('data:')) continue;" +
            "    try {" +
            "      var r = await fetch(src);" +
            "      if (r.ok) {" +
            "        var blob = await r.blob();" +
            "        var dr = new FileReader();" +
            "        var du = await new Promise(function(res) { dr.onload = function() { res(dr.result); }; dr.readAsDataURL(blob); });" +
            "        imgs[i].src = du;" +
            "      }" +
            "    } catch(e) {}" +
            "    imgs[i].removeAttribute('srcset');" +
            "  }" +
            // 完成HTMLをBase64でブリッジに渡す
            "  var html = document.documentElement.outerHTML;" +
            "  var b64 = btoa(unescape(encodeURIComponent(html)));" +
            "  SingleFileBridge.onResult(b64);" +
            "} catch(e) {" +
            "  SingleFileBridge.onError(e.toString());" +
            "}" +
            "})();";
        webView.evaluateJavascript(js, null);
    }

    private class Bridge {
        @JavascriptInterface
        public void onResult(String htmlB64) {
            final String url = currentUrl;
            new Thread(() -> {
                try {
                    byte[] bytes = Base64.decode(htmlB64, Base64.DEFAULT);
                    String html = new String(bytes, StandardCharsets.UTF_8);
                    postResult(url, html);
                } catch (Exception e) {
                    postError(url, "decode: " + e.getMessage());
                }
                fetchInProgress = false;
            }).start();
        }

        @JavascriptInterface
        public void onError(String error) {
            final String url = currentUrl;
            new Thread(() -> {
                postError(url, error);
                fetchInProgress = false;
            }).start();
        }
    }

    private String[] fetchNextUrl() {
        try {
            URL url = new URL("http://127.0.0.1:" + PORT + "/api/webview-crawl/next");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(3000);
            conn.setReadTimeout(3000);
            int code = conn.getResponseCode();
            if (code == 200) {
                String json = readStream(conn.getInputStream());
                conn.disconnect();
                String nextUrl = extractJsonString(json, "url");
                String done = extractJsonValue(json, "done");
                return new String[] { nextUrl, done };
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
}
