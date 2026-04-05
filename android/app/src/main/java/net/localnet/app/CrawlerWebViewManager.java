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
 * WebViewのfetch APIでHTMLソースだけ取得するクローラー。
 * ページをレンダリングせず、JavaScriptのfetch()でHTMLテキストだけ取得。
 * WebView(Chrome)のTLSスタックを使うのでCloudflare等に弾かれない。
 * 取得したHTMLはPython側でSingleFile化する。
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
            webView.loadUrl("about:blank");
            webView.addJavascriptInterface(new FetchBridge(), "CrawlerBridge");
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
                    mainHandler.post(() -> fetchViaJs(nextUrl));
                    long timeout = System.currentTimeMillis() + 30000;
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

    /** fetch()でHTMLソースだけ取得（レンダリングしない） */
    private void fetchViaJs(String pageUrl) {
        String js = "(async function() {" +
            "try {" +
            "  var resp = await fetch('" + escapeJs(pageUrl) + "', {" +
            "    credentials: 'include'," +
            "    headers: {'Accept': 'text/html,*/*'}" +
            "  });" +
            "  var status = resp.status;" +
            "  if (status !== 200) {" +
            "    CrawlerBridge.onError('" + escapeJs(pageUrl) + "', 'HTTP ' + status);" +
            "    return;" +
            "  }" +
            "  var buf = await resp.arrayBuffer();" +
            "  var bytes = new Uint8Array(buf);" +
            "  var binary = '';" +
            "  for (var i = 0; i < bytes.length; i++) { binary += String.fromCharCode(bytes[i]); }" +
            "  var b64 = btoa(binary);" +
            "  CrawlerBridge.onSuccess('" + escapeJs(pageUrl) + "', b64);" +
            "} catch(e) {" +
            "  CrawlerBridge.onError('" + escapeJs(pageUrl) + "', e.toString());" +
            "}" +
            "})();";
        webView.evaluateJavascript(js, null);
    }

    private class FetchBridge {
        @JavascriptInterface
        public void onSuccess(String pageUrl, String htmlB64) {
            new Thread(() -> {
                try {
                    byte[] htmlBytes = Base64.decode(htmlB64, Base64.DEFAULT);
                    // charset検出
                    String charset = detectCharset(htmlBytes);
                    String html;
                    if (charset != null && !charset.equalsIgnoreCase("utf-8")) {
                        html = new String(htmlBytes, charset);
                    } else {
                        html = new String(htmlBytes, StandardCharsets.UTF_8);
                    }
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

    private String detectCharset(byte[] data) {
        int len = Math.min(data.length, 4096);
        String head = new String(data, 0, len, StandardCharsets.ISO_8859_1).toLowerCase();
        int idx = head.indexOf("charset=");
        if (idx >= 0) {
            idx += 8;
            if (idx < head.length() && (head.charAt(idx) == '"' || head.charAt(idx) == '\'')) idx++;
            int end = idx;
            while (end < head.length() && (Character.isLetterOrDigit(head.charAt(end))
                    || head.charAt(end) == '-' || head.charAt(end) == '_')) end++;
            if (end > idx) return head.substring(idx, end);
        }
        return null;
    }

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
