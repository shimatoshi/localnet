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

import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class MainActivity extends Activity {

    private static final int PORT = 8789;
    private WebView webView;
    private TextView loadingText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        webView = findViewById(R.id.webview);
        loadingText = findViewById(R.id.loading_text);

        setupWebView();
        ensureStoragePermission();
        createImportFolder();

        // Python初期化・サーバー起動
        new Thread(() -> {
            extractAssets();
            startFlaskServer();
            waitForServer();

            new Handler(Looper.getMainLooper()).post(() -> {
                loadingText.setVisibility(View.GONE);
                webView.loadUrl("http://127.0.0.1:" + PORT);
            });
        }).start();
    }

    private void setupWebView() {
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

    private void createImportFolder() {
        // /sdcard/ShimaNet/import/ を作成
        File importDir = new File(Environment.getExternalStorageDirectory(), "ShimaNet/import");
        if (!importDir.exists()) {
            importDir.mkdirs();
        }
    }

    private String getImportFolderPath() {
        return new File(Environment.getExternalStorageDirectory(), "ShimaNet/import").getAbsolutePath();
    }

    private void extractAssets() {
        File appDir = getFilesDir();
        File cacheDir = new File(appDir, "cache");
        cacheDir.mkdirs();

        // バージョンチェック
        File versionFile = new File(appDir, ".version");
        String currentVersion = BuildConfig.VERSION_NAME;
        if (versionFile.exists()) {
            try {
                byte[] buf = new byte[64];
                InputStream is = new java.io.FileInputStream(versionFile);
                int len = is.read(buf);
                is.close();
                if (new String(buf, 0, len).trim().equals(currentVersion)) {
                    return;
                }
            } catch (IOException ignored) {}
        }

        try {
            copyAssetDir("frontend", new File(appDir, "frontend"));
        } catch (IOException e) {
            e.printStackTrace();
        }

        try {
            FileOutputStream fos = new FileOutputStream(versionFile);
            fos.write(currentVersion.getBytes());
            fos.close();
        } catch (IOException ignored) {}
    }

    private void copyAssetDir(String assetPath, File targetDir) throws IOException {
        String[] list = getAssets().list(assetPath);
        if (list == null || list.length == 0) {
            targetDir.getParentFile().mkdirs();
            InputStream is = getAssets().open(assetPath);
            OutputStream os = new FileOutputStream(targetDir);
            byte[] buf = new byte[8192];
            int len;
            while ((len = is.read(buf)) > 0) {
                os.write(buf, 0, len);
            }
            os.close();
            is.close();
        } else {
            targetDir.mkdirs();
            for (String child : list) {
                copyAssetDir(assetPath + "/" + child, new File(targetDir, child));
            }
        }
    }

    private void startFlaskServer() {
        if (!Python.isStarted()) {
            Python.start(new AndroidPlatform(this));
        }

        Python py = Python.getInstance();
        String appDir = getFilesDir().getAbsolutePath();
        String importPath = getImportFolderPath();

        // import_pathも環境変数で渡す
        py.getModule("os").callAttr("putenv", "SHIMANET_IMPORT_DIR", importPath);
        py.getModule("server_launcher").callAttr("start_server", appDir, PORT);
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
}
