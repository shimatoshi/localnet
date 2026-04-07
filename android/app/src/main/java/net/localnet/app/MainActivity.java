package net.localnet.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

import java.io.*;
import java.util.zip.GZIPInputStream;

public class MainActivity extends Activity {

    private static final int PORT = 8789;
    private WebView webView;
    private TextView loadingText;
    private Process pythonProcess;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        loadingText = findViewById(R.id.loading_text);

        setupWebView();
        ensureStoragePermission();

        new Thread(() -> {
            try {
                extractPythonBundle();
                extractAppSource();
                startPythonServer();
                waitForServer();

                new Handler(Looper.getMainLooper()).post(() -> {
                    loadingText.setVisibility(View.GONE);
                    webView.loadUrl("http://127.0.0.1:" + PORT);
                });
            } catch (Exception e) {
                e.printStackTrace();
                new Handler(Looper.getMainLooper()).post(() ->
                    loadingText.setText("Error: " + e.getMessage()));
            }
        }).start();
    }

    private void setupWebView() {
        WebView.setWebContentsDebuggingEnabled(true);
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setCacheMode(WebSettings.LOAD_DEFAULT);
        settings.setAllowFileAccess(true);
        settings.setDatabaseEnabled(true);

        webView.setWebViewClient(new WebViewClient());
        webView.setWebChromeClient(new WebChromeClient());
    }

    private void ensureStoragePermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            if (!Environment.isExternalStorageManager()) {
                try {
                    Intent intent = new Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION);
                    intent.setData(Uri.parse("package:" + getPackageName()));
                    startActivity(intent);
                } catch (Exception e) {
                    Intent intent = new Intent(Settings.ACTION_MANAGE_ALL_FILES_ACCESS_PERMISSION);
                    startActivity(intent);
                }
            }
        }
    }

    /** python-bundle.tar.gzを展開（初回またはバージョン更新時のみ） */
    private void extractPythonBundle() throws IOException {
        File pythonDir = new File(getFilesDir(), "python-bundle");
        File versionFile = new File(pythonDir, ".version");
        String currentVersion = BuildConfig.VERSION_NAME;

        if (versionFile.exists()) {
            try (BufferedReader r = new BufferedReader(new FileReader(versionFile))) {
                if (currentVersion.equals(r.readLine())) return;
            } catch (IOException ignored) {}
        }

        // 既存を削除して再展開
        deleteRecursive(pythonDir);

        try (InputStream is = getAssets().open("python-bundle.tar.gz");
             GZIPInputStream gis = new GZIPInputStream(is)) {
            extractTar(gis, getFilesDir());
        }

        // python3に実行権限付与
        File python = new File(pythonDir, "python3");
        python.setExecutable(true);

        // バージョンファイル書き込み
        try (FileWriter w = new FileWriter(versionFile)) {
            w.write(currentVersion);
        }
    }

    /** アプリソースをassetsからコピー（バージョン更新時のみ） */
    private void extractAppSource() throws IOException {
        File appDir = getFilesDir();
        File srcVersion = new File(appDir, ".src_version");
        String currentVersion = BuildConfig.VERSION_NAME;

        if (srcVersion.exists()) {
            try (BufferedReader r = new BufferedReader(new FileReader(srcVersion))) {
                if (currentVersion.equals(r.readLine())) return;
            } catch (IOException ignored) {}
        }

        // Pythonソースとfrontend
        copyAssetDir("app-source", appDir);

        // cacheとsitesディレクトリ確保
        new File(appDir, "cache").mkdirs();
        new File(appDir, "sites").mkdirs();

        try (FileWriter w = new FileWriter(srcVersion)) {
            w.write(currentVersion);
        }
    }

    /** ProcessBuilderでPythonサーバーを起動 */
    private void startPythonServer() {
        File appDir = getFilesDir();
        File pythonDir = new File(appDir, "python-bundle");
        File python = new File(pythonDir, "python3");
        File serverPy = new File(appDir, "server.py");

        String libDir = new File(pythonDir, "lib").getAbsolutePath();
        String stdlibDir = new File(pythonDir, "stdlib").getAbsolutePath();
        String siteDir = new File(pythonDir, "site-packages").getAbsolutePath();

        ProcessBuilder pb = new ProcessBuilder(
                python.getAbsolutePath(), serverPy.getAbsolutePath());
        pb.directory(appDir);
        pb.redirectErrorStream(true);

        pb.environment().put("LD_LIBRARY_PATH", libDir);
        pb.environment().put("PYTHONHOME", pythonDir.getAbsolutePath());
        pb.environment().put("PYTHONPATH", stdlibDir + ":" + siteDir + ":" + appDir.getAbsolutePath());
        pb.environment().put("LOCALNET_BASE", appDir.getAbsolutePath());
        pb.environment().put("LOCALNET_PORT", String.valueOf(PORT));

        try {
            pythonProcess = pb.start();
            // ログ出力（デバッグ用）
            new Thread(() -> {
                try (BufferedReader br = new BufferedReader(
                        new InputStreamReader(pythonProcess.getInputStream()))) {
                    String line;
                    while ((line = br.readLine()) != null) {
                        android.util.Log.i("Localnet-Python", line);
                    }
                } catch (IOException ignored) {}
            }).start();
        } catch (IOException e) {
            throw new RuntimeException("Failed to start Python server", e);
        }
    }

    private void waitForServer() {
        for (int i = 0; i < 60; i++) {
            try {
                java.net.URL url = new java.net.URL("http://127.0.0.1:" + PORT + "/api/version");
                java.net.HttpURLConnection conn = (java.net.HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(500);
                conn.setReadTimeout(500);
                int code = conn.getResponseCode();
                conn.disconnect();
                if (code == 200) return;
            } catch (Exception ignored) {}
            try { Thread.sleep(500); } catch (InterruptedException ignored) {}
        }
    }

    /** tar展開（簡易実装 — POSIX tar形式） */
    private void extractTar(InputStream is, File destDir) throws IOException {
        byte[] header = new byte[512];
        while (true) {
            int read = readFully(is, header);
            if (read < 512) break;

            // 空ブロック＝終端
            boolean allZero = true;
            for (int i = 0; i < 512; i++) {
                if (header[i] != 0) { allZero = false; break; }
            }
            if (allZero) break;

            String name = new String(header, 0, 100).trim().replace('\0', ' ').trim();
            if (name.isEmpty()) break;

            long size = parseTarOctal(header, 124, 12);
            byte type = header[156];

            File outFile = new File(destDir, name);

            if (type == '5' || name.endsWith("/")) {
                outFile.mkdirs();
            } else {
                outFile.getParentFile().mkdirs();
                try (FileOutputStream fos = new FileOutputStream(outFile)) {
                    long remaining = size;
                    byte[] buf = new byte[8192];
                    while (remaining > 0) {
                        int toRead = (int) Math.min(buf.length, remaining);
                        int n = is.read(buf, 0, toRead);
                        if (n <= 0) break;
                        fos.write(buf, 0, n);
                        remaining -= n;
                    }
                }
            }

            // 512バイト境界にスキップ
            long pad = (512 - (size % 512)) % 512;
            is.skip(pad);
        }
    }

    private int readFully(InputStream is, byte[] buf) throws IOException {
        int total = 0;
        while (total < buf.length) {
            int n = is.read(buf, total, buf.length - total);
            if (n <= 0) break;
            total += n;
        }
        return total;
    }

    private long parseTarOctal(byte[] header, int offset, int length) {
        String s = new String(header, offset, length).trim().replace('\0', ' ').trim();
        if (s.isEmpty()) return 0;
        try { return Long.parseLong(s, 8); } catch (NumberFormatException e) { return 0; }
    }

    private void deleteRecursive(File f) {
        if (f.isDirectory()) {
            File[] children = f.listFiles();
            if (children != null) {
                for (File child : children) deleteRecursive(child);
            }
        }
        f.delete();
    }

    private void copyAssetDir(String assetPath, File targetDir) throws IOException {
        String[] list = getAssets().list(assetPath);
        if (list == null || list.length == 0) {
            targetDir.getParentFile().mkdirs();
            try (InputStream is = getAssets().open(assetPath);
                 OutputStream os = new FileOutputStream(targetDir)) {
                byte[] buf = new byte[8192];
                int len;
                while ((len = is.read(buf)) > 0) os.write(buf, 0, len);
            }
        } else {
            targetDir.mkdirs();
            for (String child : list) {
                copyAssetDir(assetPath + "/" + child, new File(targetDir, child));
            }
        }
    }

    @Override
    public void onBackPressed() {
        webView.evaluateJavascript(
            "if(window.history.length > 1) { window.history.back(); 'ok'; } else { 'exit'; }",
            value -> {
                if (!"\"ok\"".equals(value)) {
                    runOnUiThread(() -> super.onBackPressed());
                }
            }
        );
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        if (pythonProcess != null) {
            pythonProcess.destroy();
        }
    }
}
