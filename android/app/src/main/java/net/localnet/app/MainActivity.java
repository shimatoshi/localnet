package net.localnet.app;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.TextView;

public class MainActivity extends Activity {

    private static final String TAG = "Localnet";
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
        requestBatteryOptimizationExemption();

        // Foreground Serviceを起動
        Intent serviceIntent = new Intent(this, ServerService.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(serviceIntent);
        } else {
            startService(serviceIntent);
        }

        // サーバー起動を待ってWebViewに表示
        new Thread(() -> {
            waitForServer();
            new Handler(Looper.getMainLooper()).post(() -> {
                loadingText.setVisibility(View.GONE);
                webView.loadUrl("http://127.0.0.1:" + PORT);
            });
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

    /** 電池の最適化を無効化するリクエスト */
    private void requestBatteryOptimizationExemption() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            PowerManager pm = getSystemService(PowerManager.class);
            if (!pm.isIgnoringBatteryOptimizations(getPackageName())) {
                try {
                    Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                    intent.setData(Uri.parse("package:" + getPackageName()));
                    startActivity(intent);
                } catch (Exception e) {
                    Log.w(TAG, "Battery optimization request failed", e);
                }
            }
        }
    }

    private void waitForServer() {
        for (int i = 0; i < 120; i++) {
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
